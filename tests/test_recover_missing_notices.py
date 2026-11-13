from __future__ import annotations

import json
from datetime import date
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_notice  # noqa: E402
import notice_catalog  # noqa: E402
import recover_missing_notices  # noqa: E402
import recovery_queue  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


class RecoverMissingNoticesTests(unittest.TestCase):
    def test_recovery_queue_persists_until_explicitly_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            queue_path = Path(temporary_directory) / "recovery_queue.json"
            with mock.patch.object(recovery_queue, "QUEUE_PATH", queue_path):
                notice_id = recovery_queue.add_notice(
                    "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&nttId=72294",
                    "IBM 제품 보안 업데이트 권고",
                )
                self.assertEqual(notice_id, "72294")
                self.assertEqual(recovery_queue.load_queue()[0][0], "72294")
                recovery_queue.remove_notice("72294")
                self.assertEqual(recovery_queue.load_queue(), [])

    def test_reads_recent_notice_from_rss(self) -> None:
        rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel><item>
          <title><![CDATA[ IBM 제품 보안 업데이트 권고 ]]></title>
          <link><![CDATA[ https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&menuNo=205020&nttId=72294 ]]></link>
        </item></channel></rss>""".encode("utf-8")
        with mock.patch.object(
            recover_missing_notices.urllib.request,
            "urlopen",
            return_value=FakeResponse(rss),
        ):
            notices = recover_missing_notices.recent_notices()

        self.assertEqual(notices[0][0], "72294")
        self.assertIn("IBM", notices[0][1])

    def test_complete_notice_requires_both_languages_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            site_root = Path(temporary_directory) / "site"
            notice_root = site_root / "notices" / "72294"
            (notice_root / "ko").mkdir(parents=True)
            (notice_root / "en").mkdir(parents=True)
            (notice_root / "ko" / "notice.txt").write_text("국문", encoding="utf-8")
            (notice_root / "en" / "notice.txt").write_text("English", encoding="utf-8")
            for language in ("ko", "en"):
                (notice_root / language / "index.html").write_text("<html></html>", encoding="utf-8")
            (notice_root / "metadata.json").write_text(
                json.dumps({"notice_id": "72294", "translation_status": "complete"}), encoding="utf-8"
            )

            with mock.patch.object(process_notice, "SITE_ROOT", site_root):
                self.assertTrue(recover_missing_notices.is_complete("72294"))
                (notice_root / "en" / "index.html").unlink()
                self.assertFalse(recover_missing_notices.is_complete("72294"))

    def test_recovery_logs_failure_and_returns_for_future_retry(self) -> None:
        notice = (
            "72294",
            "IBM 제품 보안 업데이트 권고",
            "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&nttId=72294",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            queue_path = Path(temporary_directory) / "recovery_queue.json"
            with (
                mock.patch.object(recovery_queue, "QUEUE_PATH", queue_path),
                mock.patch.object(process_notice, "SITE_ROOT", Path(temporary_directory) / "site"),
                mock.patch.object(
                    notice_catalog, "official_notices",
                    return_value=[notice_catalog.Notice(*notice, date(2026, 11, 12), 1)],
                ),
                mock.patch.object(recover_missing_notices, "is_complete", return_value=False),
                mock.patch.object(process_notice, "write_notice_index"),
                mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("formatter", 120)),
            ):
                recover_missing_notices.main()
                self.assertEqual(recovery_queue.load_queue()[0][0], "72294")

    def test_official_scan_keeps_pins_once_and_fails_on_pagination_gaps(self) -> None:
        recent = date(2026, 11, 12)
        older = date(2026, 8, 10)
        pin = notice_catalog.Notice("72230", "Pinned", "https://example.test/1", recent, None)
        first = notice_catalog.Notice("72304", "Current", "https://example.test/2", recent, 30)
        last = notice_catalog.Notice("72156", "Old", "https://example.test/3", older, 29)
        since = date(2026, 8, 12)
        with mock.patch.object(notice_catalog, "fetch_page", side_effect=[[pin, first], [pin, last]]):
            self.assertEqual(notice_catalog.official_notices(since, recent), [first, pin])
        with mock.patch.object(notice_catalog, "fetch_page", side_effect=[[pin, first], [pin, first]]):
            with self.assertRaisesRegex(RuntimeError, "pagination"):
                notice_catalog.official_notices(since, recent)

    def test_failed_request_moves_behind_untried_requests(self) -> None:
        def request(notice_id):
            return (notice_id, f"Notice {notice_id}",
                    f"https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&nttId={notice_id}")

        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            mock.patch.object(recovery_queue, "QUEUE_PATH", Path(temporary_directory) / "queue.json"),
            mock.patch.object(notice_catalog, "official_notices", return_value=[]),
            mock.patch.object(recover_missing_notices, "is_complete", return_value=False),
            mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("formatter", 120)),
        ):
            recovery_queue.write_queue([request("72294"), request("72293")])
            recover_missing_notices.main(limit=1)
            self.assertEqual([item[0] for item in recovery_queue.load_queue()], ["72293", "72294"])

    def test_discovery_records_missing_notice_before_starting_translation(self) -> None:
        entry = notice_catalog.Notice(
            "72294", "IBM notice", "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&nttId=72294",
            date(2026, 11, 12), 1,
        )
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            mock.patch.object(recovery_queue, "QUEUE_PATH", Path(temporary_directory) / "queue.json"),
            mock.patch.object(process_notice, "SITE_ROOT", Path(temporary_directory) / "site"),
            mock.patch.object(notice_catalog, "official_notices", return_value=[entry]),
            mock.patch.object(recover_missing_notices, "is_complete", return_value=False),
            mock.patch.object(process_notice, "write_notice_index"),
            mock.patch.object(subprocess, "run") as translate,
        ):
            recover_missing_notices.main(full_scan=True, discover_only=True)
            self.assertEqual(recovery_queue.load_queue(), [entry.request()])
            translate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
