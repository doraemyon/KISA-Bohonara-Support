from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_notice  # noqa: E402
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
            (notice_root / "metadata.json").write_text(
                json.dumps({"translation_status": "complete"}), encoding="utf-8"
            )

            with mock.patch.object(process_notice, "SITE_ROOT", site_root):
                self.assertTrue(recover_missing_notices.is_complete("72294"))
                (notice_root / "en" / "notice.txt").unlink()
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
                mock.patch.object(
                    recover_missing_notices, "recent_notices", return_value=[notice]
                ),
                mock.patch.object(recover_missing_notices, "is_complete", return_value=False),
                mock.patch.object(process_notice, "main", side_effect=RuntimeError("temporary")),
            ):
                recover_missing_notices.main()
                self.assertEqual(recovery_queue.load_queue()[0][0], "72294")


if __name__ == "__main__":
    unittest.main()
