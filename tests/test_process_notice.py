from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_notice  # noqa: E402


SAMPLE_HTML = """<!doctype html>
<html lang="ko"><body>
<section id="View" class="bbs">
  <div class="b_title"><h2>Ivanti 제품 보안 업데이트 권고</h2><span>2026-11-10</span></div>
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
    def test_product_security_update_title_is_stable_across_providers(self) -> None:
        self.assertEqual(
            process_notice.normalize_english_title(
                "IBM 제품 보안 업데이트 권고",
                "IBM product security update advisories",
            ),
            "IBM Product Security Update Advisory",
        )

    def test_extracts_title_paragraphs_and_table_as_utf8_text(self) -> None:
        notice = process_notice.parse_notice_document(SAMPLE_HTML)
        title, body, published_date = notice.title, notice.body, notice.published_date

        self.assertEqual(title, "Ivanti 제품 보안 업데이트 권고")
        self.assertEqual(published_date, "2026-11-10")
        self.assertIn("□ 개요\no 보안 업데이트 발표 [1]", body)
        self.assertIn(
            "취약점 / 제품명 / 영향받는 버전 / 해결 버전\n"
            "CVE-2026-111357 / Connect Secure / 22.8R2.6 미만 / 22.8R2.6 이상",
            body,
        )
        self.assertIn("[1] https://example.com", body)

    def test_only_notice_attachments_are_rendered_below_both_languages(self) -> None:
        attachment_block = """
            <div class="attach">
              <a onclick="fileDown('file_1','1','B0000133')">가이드 &amp; 설명.pdf</a>
              <a href="/common/cmm/fms/FileDown.do?atchFileId=file_1&amp;fileSn=1">duplicate</a>
              <a href="https://example.com/common/cmm/fms/FileDown.do?atchFileId=evil&amp;fileSn=1">external</a>
            </div>
        """
        source = SAMPLE_HTML.replace('<div class="content">', attachment_block + '<div class="content">')
        notice = process_notice.parse_notice_document(source)
        original = "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&nttId=72263"
        self.assertEqual(notice.attachments, ["가이드 & 설명.pdf"])
        self.assertEqual(process_notice.parse_notice_document(SAMPLE_HTML).attachments, [])
        self.assertNotIn("가이드", notice.body)
        for language, heading in (("ko", "첨부파일"), ("en", "Attachments")):
            page = process_notice.render_page(language, notice.title, notice.body, original, attachments=notice.attachments)
            self.assertIn(f"</svg>{heading}</h2>", page)
            self.assertIn("가이드 &amp; 설명.pdf", page)
            self.assertIn("nttId=72263#:~:text=", page)
            self.assertGreater(page.index('class="notice-attachments"'), page.index('id="notice-text"'))
        archive = process_notice.render_notice_index(
            [{"notice_id": "72263", "title": notice.title, "has_korean": True, "has_english": True, "has_attachments": True}]
        )
        self.assertIn('aria-label="첨부파일 있음"', archive)

    def test_keeps_explicit_breaks_without_padding_each_paragraph(self) -> None:
        paragraphs = """
            <p>□ 개요</p>
            <p>○ 첫 항목</p>
            <p>○ 둘째
            항목<br>추가 안내<br><br>별도 문단</p>
            <p>&nbsp;</p>
            <div><p>□ 대응 방안</p><p>○ 대응 절차를 확인합니다.
            - 하위 항목을 확인합니다.</p></div>
        """
        source = SAMPLE_HTML.partition('<div class="content_html">')[0]
        body = process_notice.parse_notice_document(
            source + '<div class="content_html">' + paragraphs + "</div></div></section>"
        ).body
        self.assertEqual(
            body,
            "□ 개요\n○ 첫 항목\n○ 둘째 항목\n추가 안내\n\n별도 문단\n\n"
            "□ 대응 방안\n○ 대응 절차를 확인합니다.\n- 하위 항목을 확인합니다.",
        )

    def test_update_advisory_uses_update_summary(self) -> None:
        notice = process_notice.parse_notice_document(SAMPLE_HTML)
        title, body = notice.title, notice.body
        document = process_notice.korean_document(title, body)

        self.assertTrue(process_notice.is_update_advisory(title, body))
        self.assertIn("영향 버전을 가용중인 각 관계사 담당자 분들께 업데이트 권고", document)

    def test_explicit_update_advisory_does_not_depend_on_body_keywords(self) -> None:
        title = "제품 보안 업데이트 권고"
        body = "□ 개요\no 제조사가 제품 관련 보안 공지를 발표했습니다."

        self.assertTrue(process_notice.is_update_advisory(title, body))
        self.assertIn(
            "영향 버전을 가용중인 각 관계사 담당자 분들께 업데이트 권고",
            process_notice.korean_document(title, body),
        )

    def test_security_action_advisory_with_patch_details_uses_update_summary(self) -> None:
        title = "에스티이지 제품 보안 조치 권고"
        body = (
            "□ 영향을 받는 제품 및 조치 방안\n"
            "o 영향받는 버전은 제조사의 보안 패치 또는 임시 조치를 적용"
        )

        self.assertTrue(process_notice.is_update_advisory(title, body))
        self.assertIn(
            "영향 버전을 가용중인 각 관계사 담당자 분들께 업데이트 권고",
            process_notice.korean_document(title, body),
        )

    def test_english_update_summary_matches_the_generated_korean_template(self) -> None:
        summary = process_notice.english_summary(
            "제품 보안 업데이트 권고",
            "Product Security Update Advisory",
            "□ 개요\no 보안 업데이트 발표",
        )

        self.assertEqual(
            summary,
            "We are disseminating today's KISA announcement "
            '"Product Security Update Advisory". We recommend that representatives at '
            "each affiliated company using an affected version update, and please reply "
            "if you have any specific issues.",
        )

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
            "2026-11-10",
        )

        self.assertIn('<meta charset="utf-8">', page)
        self.assertIn('id="copy-all"', page)
        self.assertIn('href="../../../assets/style.css"', page)
        self.assertIn('src="../../../assets/app.js"', page)
        self.assertIn('id="copy-status"', page)
        self.assertIn('class="notice-card"', page)
        self.assertIn('class="site-header"', page)
        self.assertIn('<time datetime="2026-11-10">발행일 2026-11-10</time>', page)
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
        self.assertIn('href="./notice.txt" download="제목 테스트.txt"', page)
        self.assertIn("제목 테스트.txt · 1 lines", page)
        self.assertIn('aria-label="제목 테스트.txt"', page)
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
        self.assertIn('download="Test advisory.txt"', english_page)
        self.assertIn("Test advisory.txt · 5 lines", english_page)

    def test_download_filename_is_safe_on_common_desktop_platforms(self) -> None:
        self.assertEqual(
            process_notice.safe_text_filename('제품: 보안/업데이트? "권고"'),
            "제품 보안 업데이트 권고.txt",
        )
        self.assertEqual(process_notice.safe_text_filename("CON"), "_CON.txt")
        self.assertEqual(process_notice.safe_text_filename("..."), "KISA security notice.txt")
        self.assertLessEqual(len(process_notice.safe_text_filename("가" * 200)), 124)

    def test_notice_index_lists_stored_languages(self) -> None:
        page = process_notice.render_notice_index(
            [
                {
                    "notice_id": "72263",
                    "title": "Ivanti 제품 보안 업데이트 권고",
                    "published_date": "2026-11-10",
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
        self.assertIn('<time datetime="2026-11-10">2026-11-10</time>', page)
        self.assertIn(process_notice.FAVICON_URL, page)
        self.assertIn(process_notice.KISA_LOGO_URL, page)

    def test_refresh_stored_pages_uses_each_document_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site_root = Path(directory)
            notice_root = site_root / "notices" / "72284"
            (notice_root / "ko").mkdir(parents=True)
            (notice_root / "en").mkdir(parents=True)
            (notice_root / "metadata.json").write_text(
                json.dumps(
                    {
                        "title": "에스티이지 제품 보안 조치 권고",
                        "published_date": "2026-11-10",
                        "source_url": (
                            "https://www.boho.or.kr/kr/bbs/view.do?"
                            "bbsId=B0000133&nttId=72284"
                        ),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (notice_root / "ko" / "notice.txt").write_text(
                "제목:\n에스티이지 제품 보안 조치 권고\n\n"
                "요약:\n이전 요약\n\n본문:\n영향받는 버전의 보안 패치 적용\n",
                encoding="utf-8",
            )
            (notice_root / "en" / "notice.txt").write_text(
                "Title:\nSTEG Product Security Action Advisory\n\n"
                "Summary:\nPrevious summary\n\nBody:\nApply the security patch.\n",
                encoding="utf-8",
            )

            with mock.patch.object(process_notice, "SITE_ROOT", site_root):
                process_notice.refresh_stored_notice_pages()

            korean_page = (notice_root / "ko" / "index.html").read_text(encoding="utf-8")
            english_page = (notice_root / "en" / "index.html").read_text(encoding="utf-8")
            self.assertIn(
                'download="에스티이지 제품 보안 조치 권고.txt"', korean_page
            )
            self.assertIn(
                'download="STEG Product Security Action Advisory.txt"', english_page
            )
            self.assertIn("Published 2026-11-10", english_page)
            normalized_english = (notice_root / "en" / "notice.txt").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "representatives at each affiliated company using an affected version",
                normalized_english,
            )

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

    def test_invalid_online_fragment_is_retried_without_retranslating_good_fragments(self) -> None:
        google_results = {
            "제품 업데이트 권고": "Product Update",
            "처음 보는 항목": "New information",
            "알 수 없는 값": "알 수 없는 값",
            "업데이트를 적용하십시오.": "Apply the update.",
        }
        with (
            mock.patch.object(
                process_notice, "translate_segment_google", side_effect=google_results.__getitem__
            ) as google,
            mock.patch.object(process_notice, "translate_segment", return_value="Unknown value") as mymemory,
            mock.patch.object(process_notice.offline_translation, "translate") as offline,
        ):
            _, translated, provider = process_notice.english_document(
                "제품 업데이트 권고",
                "□ 처음 보는 항목\n알 수 없는 값 / Connect Secure\no 업데이트를 적용하십시오. [1]",
            )

        self.assertEqual(google.call_count, 4)
        mymemory.assert_called_once_with("알 수 없는 값", "")
        offline.assert_not_called()
        self.assertEqual(provider, "google-translate-web+mymemory")
        self.assertIn("□ New information", translated)
        self.assertIn("Unknown value / Connect Secure", translated)
        self.assertIn("o Apply the update. [1]", translated)

    def test_online_outage_uses_the_offline_model_and_keeps_both_languages_valid(self) -> None:
        local = {"제품 업데이트 권고": "Product Update", "업데이트를 적용하십시오.": "Apply the update."}
        body = (
            "□ 개요\no 업데이트를 적용하십시오. [1]\n"
            "CVE-2026-12345 / Product / 7.2.1-69057-13 미만 / 7.2.1-69057-13 이상"
        )
        with (
            mock.patch.object(process_notice, "translate_segment_google", side_effect=TimeoutError) as google,
            mock.patch.object(process_notice, "translate_segment", side_effect=RuntimeError("quota")) as mymemory,
            mock.patch.object(process_notice.offline_translation, "translate", side_effect=lambda text, _accepts: local[text]),
        ):
            title, translated, provider = process_notice.english_document("제품 업데이트 권고", body)

        google.assert_called_once()
        mymemory.assert_called_once()
        self.assertEqual(provider, "offline-opus-mt")
        self.assertIn("Below 7.2.1-69057-13 / 7.2.1-69057-13 or later", translated)
        process_notice.validate_english_document(
            process_notice.korean_document("제품 업데이트 권고", body), title, translated
        )

    def test_google_translate_response_is_parsed_without_a_library_dependency(self) -> None:
        response_body = [[
            ["Apply security updates.", "보안 업데이트를 적용하십시오.", None, None]
        ], None, "ko"]

        class FakeGoogleResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps(response_body, ensure_ascii=False).encode("utf-8")

        with mock.patch.object(
            process_notice.urllib.request,
            "urlopen",
            return_value=FakeGoogleResponse(),
        ):
            translated = process_notice.translate_segment_google(
                "보안 업데이트를 적용하십시오."
            )

        self.assertEqual(translated, "Apply security updates.")

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

    def test_translation_validation_rejects_missing_structure_markers(self) -> None:
        korean = (
            "제목:\n제품 업데이트\n\n요약:\n공지입니다.\n\n본문:\n"
            "□ 개요\no 보안 업데이트 발표\n※ 참고"
        )
        valid = (
            "Title:\nProduct Update\n\nSummary:\nSecurity notice.\n\nBody:\n"
            "□ Overview\no Security update released\n※ Reference\n"
        )

        process_notice.validate_english_document(korean, "Product Update", valid)
        with self.assertRaises(RuntimeError):
            process_notice.validate_english_document(
                korean, "Product Update", valid.replace("□ Overview", "Overview")
            )

    def test_legacy_translation_structure_is_repaired_without_changing_content(self) -> None:
        korean = (
            "제목:\n제품 업데이트\n\n요약:\n공지\n\n본문:\n"
            "□ 개요\no 보안 업데이트 발표\n□ 설명\no 취약점 설명\n"
            "□ 조치 방법\no 최신 버전 적용"
        )
        legacy = (
            "Title:\nProduct Update\n\nSummary:\nNotice\n\nBody:\n"
            "Course Overview\nSecurity update released\nDescription\n"
            "Vulnerability details\nHow to □ take action\no Apply the latest version\n"
        )

        normalized = process_notice.normalize_english_sections(legacy)
        repaired = process_notice.repair_legacy_english_bullets(korean, normalized)

        self.assertIn("□ Overview", repaired)
        self.assertIn("□ Description", repaired)
        self.assertIn("□ Remediation steps", repaired)
        self.assertIn("o Security update released", repaired)
        self.assertIn("o Vulnerability details", repaired)

    def test_translation_placeholders_restore_urls_cves_and_versions(self) -> None:
        source = (
            "CVE-2026-11724 / 9.4.5.1 / "
            "https://example.com/security/CVE-2026-11724?version=9.4.5.1"
        )

        masked, replacements = process_notice.mask_protected_tokens(source)

        self.assertNotIn("CVE-2026-11724", masked)
        self.assertNotIn("9.4.5.1", masked)
        self.assertNotIn("https://", masked)
        self.assertGreaterEqual(masked.count("KISAPROTECTEDTOKEN"), 3)
        self.assertEqual(
            process_notice.restore_protected_tokens(masked.lower(), replacements),
            source,
        )

    def test_hyphenated_builds_keep_their_full_values_and_comparison_bounds(self) -> None:
        source = "CVE-2026-12345 / DSM 7.2.1 / 7.2.1-69057-13 미만 / 7.2.1-69057-13이상"
        translator = mock.Mock(side_effect=AssertionError("Version cells must stay local."))

        translated = process_notice.translate_text_linewise(source, translator)

        self.assertEqual(
            translated,
            "CVE-2026-12345 / DSM 7.2.1 / Below 7.2.1-69057-13 / 7.2.1-69057-13 or later",
        )
        self.assertEqual(
            process_notice.protected_tokens(translated), process_notice.protected_tokens(source)
        )
        translator.assert_not_called()

    def test_translation_validation_rejects_a_changed_build_suffix(self) -> None:
        korean = "제목:\n제품 업데이트\n\n요약:\n공지입니다.\n\n본문:\n7.3.2-86009-5 이상"
        english = "Title:\nProduct Update\n\nSummary:\nSecurity notice.\n\nBody:\n7.3.2-86009-6 or later\n"

        with self.assertRaisesRegex(RuntimeError, "omitted protected values: 7.3.2-86009-5"):
            process_notice.validate_english_document(korean, "Product Update", english)

    def test_translation_validation_rejects_versions_swapped_between_columns(self) -> None:
        korean = (
            "제목:\n제품 업데이트\n\n요약:\n공지입니다.\n\n본문:\n"
            "CVE-2026-12345 / Product / 1.2.3 / 1.2.4"
        )
        english = (
            "Title:\nProduct Update\n\nSummary:\nSecurity notice.\n\nBody:\n"
            "CVE-2026-12345 / Product / 1.2.4 / 1.2.3\n"
        )
        with self.assertRaisesRegex(RuntimeError, "moved protected values between cells"):
            process_notice.validate_english_document(korean, "Product Update", english)

    def test_table_headers_and_range_inclusivity_do_not_depend_on_the_provider(self) -> None:
        source = (
            "취약점 / 제품명 / 영향받는 버전 / 해결 버전\n"
            "CVE-2026-12345 / Product / 19.0.0 이상 19.0R2.9 미만 / 19.0.9 PL1 이상"
        )
        translator = mock.Mock(side_effect=AssertionError("Table labels and bounds are structured."))

        translated = process_notice.translate_text_linewise(source, translator)

        self.assertEqual(
            translated,
            "Vulnerability / Product Name / Affected Version / Fixed Version\n"
            "CVE-2026-12345 / Product / 19.0.0 or later and below 19.0R2.9 / 19.0.9 PL1 or later",
        )
        translator.assert_not_called()

    def test_parentheses_around_a_cve_are_preserved_outside_the_provider(self) -> None:
        translator = mock.Mock(return_value="Memory read vulnerability")
        translated = process_notice.translate_text_linewise("o 메모리 읽기 취약점(CVE-2026-12345) [1]", translator)
        self.assertEqual(translated, "o Memory read vulnerability (CVE-2026-12345) [1]")
        translator.assert_called_once_with("메모리 읽기 취약점")

    def test_cve_table_uses_standard_impact_terms_and_retains_the_product_name(self) -> None:
        source = (
            "제품 카테고리 / CVE 번호 / CVE 제목\n"
            "Windows / CVE-2026-12345 / Windows DPAPI (Data Protection API) 권한 상승 취약성"
        )
        translator = mock.Mock(side_effect=AssertionError("Known table terms stay local."))
        self.assertEqual(
            process_notice.translate_text_linewise(source, translator),
            "Product Category / CVE ID / CVE Title\n"
            "Windows / CVE-2026-12345 / Windows DPAPI (Data Protection API) Elevation of Privilege Vulnerability",
        )
        translator.assert_not_called()

    def test_main_publishes_nothing_until_both_languages_are_ready(self) -> None:
        title = "IBM 제품 보안 업데이트 권고"
        body = "□ 개요\no 9.4.5.1 미만 버전은 최신 버전으로 업데이트 권고"
        notice_url = (
            "https://www.boho.or.kr/kr/bbs/view.do?"
            "bbsId=B0000133&menuNo=205020&nttId=72294"
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            site_root = Path(temporary_directory) / "site"
            with (
                mock.patch.object(process_notice, "SITE_ROOT", site_root),
                mock.patch.object(
                    process_notice,
                    "fetch_notice",
                    return_value=process_notice.NoticeDocument(title, body, "2026-11-10", []),
                ),
                mock.patch.object(
                    process_notice,
                    "english_document",
                    side_effect=TimeoutError("translation provider timed out"),
                ),
                mock.patch.dict(
                    process_notice.os.environ,
                    {
                        "NOTICE_URL": notice_url,
                        "NOTICE_TITLE": title,
                        "GITHUB_OUTPUT": "",
                        "GEMINI_API_KEY": "test-key",
                    },
                ),
            ):
                with self.assertRaises(TimeoutError):
                    process_notice.main()

            self.assertFalse((site_root / "notices" / "72294").exists())

    def test_google_translation_is_used_when_configured_providers_fail(self) -> None:
        translations = {"제품 업데이트 권고": "Product Update", "업데이트를 적용하십시오.": "Apply the update."}
        with (
            mock.patch.object(process_notice, "translate_with_gemini") as gemini,
            mock.patch.object(process_notice, "translate_segment_cloudflare", side_effect=RuntimeError("down")),
            mock.patch.object(
                process_notice,
                "translate_segment_google",
                side_effect=translations.__getitem__,
            ),
            mock.patch.object(process_notice, "translate_segment") as mymemory,
        ):
            title, document, provider = process_notice.english_document(
                "제품 업데이트 권고",
                "□ 개요\no 업데이트를 적용하십시오.",
                "gemini-key",
                process_notice.DEFAULT_GEMINI_MODEL,
                "0123456789abcdef0123456789abcdef",
                "cloudflare-token",
                "",
            )

        self.assertEqual(title, "Product Update")
        self.assertIn(
            'Summary:\nWe are disseminating today\'s KISA announcement "Product Update".',
            document,
        )
        self.assertIn("Body:\n□ Overview\no Apply the update.", document)
        self.assertEqual(provider, "google-translate-web")
        gemini.assert_not_called()
        mymemory.assert_not_called()

    def test_gemini_timeout_switches_to_mymemory_after_one_attempt(self) -> None:
        translations = {"제품 업데이트 권고": "Product Update", "업데이트를 적용하십시오.": "Apply the update."}
        with (
            mock.patch.object(process_notice, "translate_segment_google", side_effect=RuntimeError("HTTP 429")),
            mock.patch.object(process_notice, "translate_with_gemini", side_effect=TimeoutError) as gemini,
            mock.patch.object(process_notice, "translate_segment", side_effect=lambda text, _email: translations[text]),
        ):
            _, _, provider = process_notice.english_document(
                "제품 업데이트 권고", "□ 개요\no 업데이트를 적용하십시오.", gemini_api_key="test-key"
            )
        self.assertEqual(provider, "mymemory")
        self.assertEqual(gemini.call_count, 1)
        self.assertEqual(gemini.call_args.kwargs, {"timeout": 20, "attempts": 1})

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
        prompt = request_json["contents"][0]["parts"][0]["text"]
        self.assertIn("제품 업데이트", prompt)
        self.assertNotIn("CVE-2026-111357", prompt)
        self.assertNotIn("22.8R2.6", prompt)
        self.assertIn("KISAPROTECTEDTOKEN", prompt)

if __name__ == "__main__":
    unittest.main()
