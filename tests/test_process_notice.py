from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock


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
        self.assertIn('class="notice-card"', page)
        self.assertIn('class="site-header"', page)
        self.assertIn('class="button button--primary"', page)
        self.assertIn('class="site-brand" href="../../../"', page)
        self.assertIn(process_notice.KISA_LOGO_URL, page)
        self.assertIn('class="language-menu__summary"', page)
        self.assertIn('href="../ko/" aria-current="page"', page)
        self.assertIn('href="../en/"', page)
        self.assertIn('rel="icon"', page)
        self.assertIn('data-line="1"', page)
        self.assertIn('class="line-content"', page)
        self.assertNotIn("<pre", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)

        english_page = process_notice.render_page(
            "en",
            "Test advisory",
            "Title:\nTest advisory\n\nBody:\nTest body",
            "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&amp;nttId=1",
        )
        self.assertIn('href="../ko/"', english_page)
        self.assertIn('href="../en/" aria-current="page"', english_page)

    def test_notice_index_lists_stored_languages(self) -> None:
        page = process_notice.render_notice_index(
            [
                {
                    "notice_id": "72263",
                    "title": "Ivanti 제품 보안 업데이트 권고",
                    "has_korean": True,
                    "has_english": True,
                }
            ]
        )

        self.assertIn("저장된 보안공지 목록", page)
        self.assertIn("총 1건", page)
        self.assertIn("Ivanti 제품 보안 업데이트 권고", page)
        self.assertIn('href="notices/72263/ko/">국문</a>', page)
        self.assertIn('href="notices/72263/en/">영문</a>', page)
        self.assertIn(process_notice.FAVICON_URL, page)
        self.assertIn(process_notice.KISA_LOGO_URL, page)

    def test_copy_script_excludes_generated_line_numbers(self) -> None:
        script = (
            Path(__file__).resolve().parents[1] / "site" / "assets" / "app.js"
        ).read_text(encoding="utf-8")
        styles = (
            Path(__file__).resolve().parents[1] / "site" / "assets" / "style.css"
        ).read_text(encoding="utf-8")

        self.assertIn('querySelectorAll(".line-content")', script)
        self.assertIn('join("\\n")', script)
        self.assertIn(".code-line::before", styles)
        self.assertIn("user-select: none", styles)

    def test_styles_use_github_dark_palette(self) -> None:
        styles = (
            Path(__file__).resolve().parents[1] / "site" / "assets" / "style.css"
        ).read_text(encoding="utf-8")

        self.assertIn("color-scheme: dark", styles)
        self.assertIn("--canvas-default: #0d1117", styles)
        self.assertIn("--canvas-subtle: #151b23", styles)
        self.assertIn("--border-default: #3d444d", styles)

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

    def test_mymemory_fallback_translates_unknown_text_dynamically(self) -> None:
        calls: list[str] = []

        def fake_translate(segment: str, _contact_email: str = "") -> str:
            calls.append(segment)
            return f"Translated text {len(calls)}"

        with mock.patch.object(process_notice, "translate_segment", side_effect=fake_translate):
            translated = process_notice.translate_text_mymemory(
                "□ 처음 보는 항목\n알 수 없는 값 / Connect Secure"
            )

        self.assertEqual(len(calls), 2)
        self.assertIn("Translated text 1", translated)
        self.assertIn("Translated text 2 / Connect Secure", translated)
        self.assertNotRegex(translated, r"[가-힣]")

    def test_translation_validation_preserves_security_identifiers(self) -> None:
        korean = (
            "제목:\n제품 업데이트\n\n요약:\n공지입니다.\n\n본문:\n"
            "CVE-2026-111357 / 22.8R2.6 / https://example.com/advisory"
        )
        valid = (
            "Title:\nProduct Update\n\nSummary:\nSecurity notice.\n\nBody:\n"
            "CVE-2026-111357 / 22.8R2.6 / https://example.com/advisory\n"
        )

        process_notice.validate_english_document(korean, "Product Update", valid)

        with self.assertRaises(RuntimeError):
            process_notice.validate_english_document(
                korean,
                "Product Update",
                valid.replace("CVE-2026-111357", "the vulnerability"),
            )

    def test_gemini_translates_the_complete_document_with_structured_output(self) -> None:
        korean = (
            "제목:\n제품 업데이트\n\n요약:\n공지입니다.\n\n본문:\n"
            "CVE-2026-111357 / 22.8R2.6 / https://example.com/advisory\n"
        )
        document = (
            "Title:\nProduct Update\n\nSummary:\nSecurity notice.\n\nBody:\n"
            "CVE-2026-111357 / 22.8R2.6 / https://example.com/advisory\n"
        )
        response_body = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {"title": "Product Update", "document": document}
                                )
                            }
                        ]
                    }
                }
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps(response_body).encode("utf-8")

        observed_request = None

        def fake_urlopen(request, timeout=0):
            nonlocal observed_request
            observed_request = request
            self.assertEqual(timeout, 60)
            return FakeResponse()

        with mock.patch.object(process_notice.urllib.request, "urlopen", side_effect=fake_urlopen):
            title, translated = process_notice.translate_with_gemini(
                korean, "test-api-key", "gemini-test-model"
            )

        self.assertEqual(title, "Product Update")
        self.assertEqual(translated, document)
        self.assertEqual(observed_request.get_header("X-goog-api-key"), "test-api-key")
        request_json = json.loads(observed_request.data.decode("utf-8"))
        self.assertEqual(
            request_json["generationConfig"]["responseMimeType"], "application/json"
        )
        self.assertIn(korean.strip(), request_json["contents"][0]["parts"][0]["text"])

if __name__ == "__main__":
    unittest.main()
