from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_notice  # noqa: E402


SAMPLE_HTML = """<!doctype html>
<html lang="ko"><body>
<section id="View" class="bbs">
  <div class="b_title"><h2>Ivanti 제품 보안 업데이트 권고</h2></div>
  <div class="content"><div class="content_html">
    <div><p>□ 개요<br><span> </span>o 보안 업데이트 발표 [1]<br>
    <span> </span>o 영향을 받는 버전은 최신 버전으로 업데이트 권고</p>
    <p>□ 영향을 받는 제품 및 해결 방안</p>
    <table><thead><tr><th>취약점</th><th>제품명</th><th>영향받는 버전</th><th>해결 버전</th></tr></thead>
    <tbody><tr><td>CVE-2026-111357</td><td>Connect Secure</td><td>22.8R2.6 미만</td><td>22.8R2.6 이상</td></tr></tbody></table>
    <p>□ 참고사이트<br>[1] <a href="https://example.com">https://example.com</a></p></div>
  </div></div>
</section></body></html>"""


class ProcessNoticeTests(unittest.TestCase):
    def test_extracts_title_paragraphs_and_table_as_utf8_text(self) -> None:
        title, body = process_notice.parse_notice_document(SAMPLE_HTML)

        self.assertEqual(title, "Ivanti 제품 보안 업데이트 권고")
        self.assertIn("□ 개요\no 보안 업데이트 발표 [1]", body)
        self.assertIn(
            "취약점 / 제품명 / 영향받는 버전 / 해결 버전\n"
            "CVE-2026-111357 / Connect Secure / 22.8R2.6 미만 / 22.8R2.6 이상",
            body,
        )
        self.assertIn("[1] https://example.com", body)

    def test_update_advisory_uses_update_summary(self) -> None:
        title, body = process_notice.parse_notice_document(SAMPLE_HTML)
        document = process_notice.korean_document(title, body)

        self.assertTrue(process_notice.is_update_advisory(title, body))
        self.assertIn("영향 버전을 가용중인 각 관계사 담당자 분들께 업데이트 권고", document)

    def test_non_update_notice_uses_general_summary(self) -> None:
        title = "최근 사이버공격 대비 기업 보안강화 권고"
        body = "□ 개요\no 최근 위협 동향에 따른 보안강화를 권고합니다."
        document = process_notice.korean_document(title, body)

        self.assertFalse(process_notice.is_update_advisory(title, body))
        self.assertIn(
            f'금일 KISA 공지 "{title}" 전파드리오니, 특이사항 있으시면 회신 바랍니다.',
            document,
        )
        self.assertNotIn("영향 버전을", document)

    def test_rejects_non_kisa_and_wrong_board_urls(self) -> None:
        with self.assertRaises(RuntimeError):
            process_notice.validate_notice_url("https://example.com/kr/bbs/view.do?bbsId=B0000133&nttId=1")
        with self.assertRaises(RuntimeError):
            process_notice.validate_notice_url("https://www.boho.or.kr/kr/bbs/view.do?bbsId=OTHER&nttId=1")

    def test_rendered_page_is_utf8_copyable_and_escaped(self) -> None:
        page = process_notice.render_page(
            "ko",
            "제목 <테스트>",
            "본문 <script>alert(1)</script>",
            "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&amp;nttId=1",
        )

        self.assertIn('<meta charset="utf-8">', page)
        self.assertIn('id="copy-all"', page)
        self.assertIn('href="../../../assets/style.css"', page)
        self.assertIn('src="../../../assets/app.js"', page)
        self.assertIn('id="copy-status"', page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_translation_chunks_stay_below_provider_byte_limit(self) -> None:
        text = "영향을 받는 사용자는 최신 버전으로 업데이트하시기 바랍니다. " * 30
        chunks = process_notice.split_utf8_chunks(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.encode("utf-8")) <= 450 for chunk in chunks))
        self.assertEqual(" ".join(chunks), text.strip())

    def test_rejects_unchanged_korean_as_english_translation(self) -> None:
        korean = "제목:\n제품 보안 업데이트 권고\n\n본문:\n최신 버전으로 업데이트하십시오."
        valid_english = "Title:\nProduct Security Update Advisory\n\nBody:\nUpdate to the latest version."

        self.assertFalse(process_notice.looks_like_english_translation(korean, korean))
        self.assertTrue(process_notice.looks_like_english_translation(korean, valid_english))

    def test_security_headings_and_version_table_use_fixed_terms(self) -> None:
        self.assertEqual(process_notice.translate_line("□ 개요"), "□ Overview")
        self.assertEqual(
            process_notice.translate_line("취약점 / 제품명 / 영향받는 버전 / 해결 버전"),
            "Vulnerability / Product / Affected versions / Fixed versions",
        )
        self.assertEqual(
            process_notice.translate_line(
                "CVE-2026-111357 / Connect Secure / 22.8R2.6 미만 / 22.8R2.6 이상"
            ),
            "CVE-2026-111357 / Connect Secure / Earlier than 22.8R2.6 / 22.8R2.6 or later",
        )
        self.assertEqual(
            process_notice.translate_line(
                "o 영향을 받는 버전을 사용 중인 사용자는 해결 방안에 따라 최신 버전으로 업데이트 권고"
            ),
            "o Users running an affected version are advised to update to the latest version "
            "according to the remediation guidance.",
        )

if __name__ == "__main__":
    unittest.main()
