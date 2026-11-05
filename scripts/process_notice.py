#!/usr/bin/env python3
"""Fetch, format, translate, and render one KISA security notice."""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


MAX_PAGE_BYTES = 2_000_000
SITE_ROOT = Path("site")
KISA_HOSTS = {"boho.or.kr", "www.boho.or.kr"}
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
MAX_TRANSLATION_BYTES = 450
FORMAT_VERSION = 3
HEADING_TRANSLATIONS = {
    "개요": "Overview",
    "설명": "Description",
    "영향을 받는 제품 및 해결 방안": "Affected Products and Remediation",
    "영향받는 제품 및 해결 방안": "Affected Products and Remediation",
    "참고사이트": "References",
    "참고 사이트": "References",
    "문의사항": "Contact",
}
SPECIAL_LINE_TRANSLATIONS = {
    "o 영향을 받는 버전을 사용 중인 사용자는 해결 방안에 따라 최신 버전으로 업데이트 권고": (
        "o Users running an affected version are advised to update to the latest version "
        "according to the remediation guidance."
    ),
    "※ 하단의 참고 사이트를 확인하여 업데이트 수행 [1]": (
        "※ Apply the update by following the reference below [1]"
    ),
    "o 한국인터넷진흥원 사이버민원센터 : 국번없이 118": (
        "o KISA Cyber Civil Complaint Center: 118 (no area code)"
    ),
}
ORGANIZATION_TRANSLATIONS = {
    "디지털위협대응본부 취약점관리센터": (
        "Vulnerability Management Center, Digital Threat Response Division"
    ),
}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def fail(message: str) -> None:
    raise RuntimeError(message)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        fail(f"Required value {name} is empty or missing.")
    return value


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if node.tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == wanted:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def has_class(node: Node, class_name: str) -> bool:
    return class_name in node.attrs.get("class", "").split()


def walk(node: Node) -> Iterable[Node]:
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from walk(child)


def first_descendant(node: Node, *, tag: str | None = None, class_name: str | None = None) -> Node | None:
    for candidate in walk(node):
        if tag is not None and candidate.tag != tag:
            continue
        if class_name is not None and not has_class(candidate, class_name):
            continue
        return candidate
    return None


def plain_inline(node: Node | str) -> str:
    if isinstance(node, str):
        return re.sub(r"\s+", " ", node)
    if node.tag == "br":
        return "\n"
    if node.tag == "img":
        return node.attrs.get("alt", "")
    return "".join(plain_inline(child) for child in node.children)


def render_table(node: Node) -> str:
    lines: list[str] = []
    for row in (candidate for candidate in walk(node) if candidate.tag == "tr"):
        cells = [
            normalize_inline(plain_inline(cell))
            for cell in row.children
            if isinstance(cell, Node) and cell.tag in {"th", "td"}
        ]
        if cells:
            lines.append(" / ".join(cells))
    return "\n".join(lines) + ("\n\n" if lines else "")


def render_body(node: Node | str) -> str:
    if isinstance(node, str):
        return re.sub(r"[\t\r\f\v ]+", " ", node)
    if node.tag == "br":
        return "\n"
    if node.tag == "table":
        return render_table(node)
    if node.tag in {"script", "style", "noscript"}:
        return ""
    rendered = "".join(render_body(child) for child in node.children)
    if node.tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}:
        return rendered + "\n\n"
    if node.tag == "li":
        return f"- {rendered.strip()}\n"
    return rendered


def normalize_inline(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_document(value: str) -> str:
    lines = [re.sub(r"[\t ]+", " ", line).strip() for line in value.splitlines()]
    normalized: list[str] = []
    for line in lines:
        if not line and (not normalized or not normalized[-1]):
            continue
        normalized.append(line)
    return "\n".join(normalized).strip()


def validate_notice_url(value: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in KISA_HOSTS:
        fail("NOTICE_URL must be an HTTPS URL on the KISA boho.or.kr host.")
    if parsed.username or parsed.password or parsed.port:
        fail("NOTICE_URL must not contain credentials or a custom port.")
    if parsed.path != "/kr/bbs/view.do":
        fail("NOTICE_URL is not a KISA notice-view URL.")
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("bbsId") != ["B0000133"]:
        fail("NOTICE_URL is not from the KISA security-notice board.")
    notice_ids = query.get("nttId", [])
    if len(notice_ids) != 1 or not re.fullmatch(r"\d{1,20}", notice_ids[0]):
        fail("NOTICE_URL has no valid numeric nttId.")
    return value, notice_ids[0]


def parse_notice_document(document: str) -> tuple[str, str]:
    parser = DocumentParser()
    parser.feed(document)
    view = next(
        (node for node in walk(parser.root) if node.tag == "section" and node.attrs.get("id") == "View"),
        None,
    )
    if view is None:
        fail("Could not find the KISA notice container.")
    title_box = first_descendant(view, class_name="b_title")
    title_node = first_descendant(title_box, tag="h2") if title_box else None
    content_node = first_descendant(view, class_name="content_html")
    if title_node is None or content_node is None:
        fail("Could not find the KISA notice title or body.")

    title = normalize_inline(plain_inline(title_node))
    body = normalize_document(render_body(content_node))
    if not title or len(body) < 20:
        fail("KISA notice title or body was unexpectedly empty.")
    return title, body


def fetch_notice(url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "kisa-notice-formatter/1.0 (+GitHub Actions)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            validate_notice_url(response.geturl())
            raw = response.read(MAX_PAGE_BYTES + 1)
    except urllib.error.HTTPError as error:
        fail(f"KISA returned HTTP {error.code}.")
    except urllib.error.URLError as error:
        fail(f"Could not reach KISA: {error.reason}")
    if len(raw) > MAX_PAGE_BYTES:
        fail("KISA page exceeded the allowed response size.")

    try:
        document = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        fail(f"KISA page was not valid UTF-8: {error}")
    return parse_notice_document(document)


def is_update_advisory(title: str, body: str) -> bool:
    title_matches = re.search(r"업데이트(?:\s*권고)?", title) is not None
    remediation_matches = re.search(
        r"CVE-\d{4}-\d+|영향(?:을\s*)?받는\s*버전|영향받는\s*제품|"
        r"취약\s*버전|해결\s*버전|조치\s*방안|해결\s*방안|최신\s*버전",
        body,
        flags=re.IGNORECASE,
    ) is not None
    return title_matches and remediation_matches


def korean_document(title: str, body: str) -> str:
    if is_update_advisory(title, body):
        summary = (
            f'금일 KISA 공지 "{title}" 전파드리오니, 영향 버전을 가용중인 각 관계사 '
            "담당자 분들께 업데이트 권고 드리며 특이사항 있으시면 회신 바랍니다."
        )
    else:
        summary = f'금일 KISA 공지 "{title}" 전파드리오니, 특이사항 있으시면 회신 바랍니다.'
    return f"제목:\n{title}\n\n요약:\n{summary}\n\n본문:\n{body}\n"


def split_utf8_chunks(value: str, max_bytes: int = MAX_TRANSLATION_BYTES) -> list[str]:
    """Split text on word boundaries below MyMemory's 500-byte request limit."""
    if len(value.encode("utf-8")) <= max_bytes:
        return [value]

    chunks: list[str] = []
    current = ""
    for word in value.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate.encode("utf-8")) > max_bytes:
            chunks.append(current)
            current = ""
        if len(word.encode("utf-8")) <= max_bytes:
            current = f"{current} {word}".strip()
            continue

        # URLs and unusually long tokens have no safe word boundary. Split by
        # Unicode code point while keeping every request under the byte limit.
        if current:
            chunks.append(current)
            current = ""
        piece = ""
        for character in word:
            if piece and len((piece + character).encode("utf-8")) > max_bytes:
                chunks.append(piece)
                piece = ""
            piece += character
        current = piece
    if current:
        chunks.append(current)
    return chunks


def translate_segment(segment: str, contact_email: str = "") -> str:
    parameters = {"q": segment, "langpair": "ko|en", "mt": "1"}
    if contact_email:
        parameters["de"] = contact_email
    request = urllib.request.Request(
        f"{MYMEMORY_URL}?{urllib.parse.urlencode(parameters)}",
        headers={"User-Agent": "kisa-notice-formatter/1.1 (+GitHub Actions)"},
    )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            status = result.get("responseStatus")
            translated = result.get("responseData", {}).get("translatedText")
            if str(status) != "200" or not isinstance(translated, str) or not translated.strip():
                details = str(result.get("responseDetails", "unknown response"))[:300]
                raise RuntimeError(f"MyMemory rejected the request: {details}")
            return html.unescape(translated.strip())
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    fail(f"MyMemory translation failed after three attempts: {last_error}")


def looks_like_english_translation(korean: str, english: str) -> bool:
    if normalize_document(korean) == normalize_document(english):
        return False
    source_hangul = len(re.findall(r"[가-힣]", korean))
    target_hangul = len(re.findall(r"[가-힣]", english))
    english_letters = len(re.findall(r"[A-Za-z]", english))
    if source_hangul and target_hangul > max(8, source_hangul // 4):
        return False
    minimum_english_letters = max(10, min(30, source_hangul // 2))
    return english_letters >= minimum_english_letters


def translate_version_phrase(value: str) -> str | None:
    stripped = value.strip()
    earlier = re.fullmatch(r"(.+?)\s*미만", stripped)
    if earlier:
        return f"Earlier than {earlier.group(1).strip()}"
    later = re.fullmatch(r"(.+?)\s*이상", stripped)
    if later:
        return f"{later.group(1).strip()} or later"
    return None


def translate_line(line: str, contact_email: str = "") -> str:
    stripped = line.strip()
    if not stripped or re.fullmatch(r"(?:\[\d+\]\s+)?https?://\S+", stripped):
        return line

    if stripped in SPECIAL_LINE_TRANSLATIONS:
        return SPECIAL_LINE_TRANSLATIONS[stripped]

    if stripped == "취약점 / 제품명 / 영향받는 버전 / 해결 버전":
        return "Vulnerability / Product / Affected versions / Fixed versions"

    if " / " in stripped:
        translated_cells: list[str] = []
        for cell in stripped.split(" / "):
            fixed_version = translate_version_phrase(cell)
            if fixed_version is not None:
                translated_cells.append(fixed_version)
            elif re.fullmatch(r"CVE-\d{4}-\d+|[A-Za-z0-9_.+-]+(?:\s+[A-Za-z0-9_.+-]+)*", cell):
                translated_cells.append(cell)
            else:
                translated_cells.append(
                    " ".join(translate_segment(chunk, contact_email) for chunk in split_utf8_chunks(cell))
                )
        return " / ".join(translated_cells)

    if stripped.startswith("□"):
        heading = stripped.removeprefix("□").strip()
        if heading.startswith("작성"):
            organization = heading.split(":", 1)[1].strip() if ":" in heading else heading
            translated_org = ORGANIZATION_TRANSLATIONS.get(organization)
            if translated_org is None:
                translated_org = " ".join(
                    translate_segment(chunk, contact_email)
                    for chunk in split_utf8_chunks(organization)
                )
            return f"□ Prepared by: {translated_org}"
        translated_heading = HEADING_TRANSLATIONS.get(heading)
        if translated_heading is None:
            translated_heading = " ".join(
                translate_segment(chunk, contact_email) for chunk in split_utf8_chunks(heading)
            )
        return f"□ {translated_heading}"

    prefix = ""
    content = stripped
    if stripped.startswith("o "):
        prefix = "o "
        content = stripped[2:]
    translated = " ".join(
        translate_segment(chunk, contact_email) for chunk in split_utf8_chunks(content)
    )
    return prefix + translated


def translate_to_english(korean: str, contact_email: str = "") -> str:
    if contact_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact_email):
        fail("MYMEMORY_CONTACT_EMAIL is not a valid email address.")

    translated_lines = [translate_line(line, contact_email) for line in korean.splitlines()]
    translated = "\n".join(translated_lines).rstrip() + "\n"
    if not looks_like_english_translation(korean, translated):
        fail("Translation result validation failed because the output was not meaningfully English.")
    return translated


def english_document(title: str, body: str, contact_email: str = "") -> tuple[str, str]:
    english_title = translate_line(title, contact_email)
    english_body = translate_to_english(body, contact_email)
    if is_update_advisory(title, body):
        summary = (
            f'Today, we are forwarding the KISA notice "{english_title}". Personnel responsible '
            "for affected systems at each affiliated company are advised to apply the update and "
            "reply if there are any notable issues."
        )
    else:
        summary = (
            f'Today, we are forwarding the KISA notice "{english_title}". '
            "Please reply if there are any notable issues."
        )
    document = f"Title:\n{english_title}\n\nSummary:\n{summary}\n\nBody:\n{english_body}"
    if not looks_like_english_translation(korean_document(title, body), document):
        fail("Final English notice validation failed.")
    return english_title, document


def render_page(language: str, title: str, notice_text: str, source_url: str) -> str:
    labels = {
        "ko": ("전체 내용 복사하기", "텍스트 파일 저장", "KISA 원문 열기"),
        "en": ("Copy all text", "Download text file", "Open KISA source"),
    }
    copy_label, download_label, source_label = labels[language]
    return f"""<!doctype html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="../../../assets/style.css">
</head>
<body>
  <main>
    <div class="toolbar">
      <button id="copy-all" type="button" data-success="{'복사 완료' if language == 'ko' else 'Copied'}" data-failure="{'복사 실패 — 텍스트를 직접 선택하세요' if language == 'ko' else 'Copy failed — select the text manually'}">{copy_label}</button>
      <span id="copy-status" class="copy-status" role="status" aria-live="polite"></span>
      <a class="button secondary" href="./notice.txt" download>{download_label}</a>
      <a class="source" href="{html.escape(source_url, quote=True)}" target="_blank" rel="noreferrer">{source_label}</a>
    </div>
    <pre id="notice-text">{html.escape(notice_text.rstrip())}</pre>
  </main>
  <script src="../../../assets/app.js" defer></script>
</body>
</html>
"""


def write_notice(
    notice_id: str,
    source_url: str,
    korean_title: str,
    english_title: str,
    korean: str,
    english: str,
) -> None:
    for language, page_title, text in (
        ("ko", korean_title, korean),
        ("en", english_title, english),
    ):
        target = SITE_ROOT / "notices" / notice_id / language
        target.mkdir(parents=True, exist_ok=True)
        (target / "notice.txt").write_text(text, encoding="utf-8", newline="\n")
        (target / "index.html").write_text(
            render_page(language, page_title, text, source_url),
            encoding="utf-8",
            newline="\n",
        )
    metadata = {
        "format_version": FORMAT_VERSION,
        "notice_id": notice_id,
        "source_url": source_url,
    }
    metadata_path = SITE_ROOT / "notices" / notice_id / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    requested_url, notice_id = validate_notice_url(required_env("NOTICE_URL"))
    expected_title = required_env("NOTICE_TITLE")
    title, body = fetch_notice(requested_url)
    if normalize_inline(expected_title) != title:
        print("WARNING: RSS title differed from the page title; using the page title.", file=sys.stderr)

    korean = korean_document(title, body)
    cached_ko = SITE_ROOT / "notices" / notice_id / "ko" / "notice.txt"
    cached_en = SITE_ROOT / "notices" / notice_id / "en" / "notice.txt"
    metadata_path = SITE_ROOT / "notices" / notice_id / "metadata.json"
    cached_english = cached_en.read_text(encoding="utf-8") if cached_en.exists() else ""
    try:
        cached_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cached_metadata = {}
    if (
        cached_ko.exists()
        and cached_ko.read_text(encoding="utf-8") == korean
        and looks_like_english_translation(korean, cached_english)
        and cached_metadata.get("format_version") == FORMAT_VERSION
    ):
        english = cached_english
        english_lines = english.splitlines()
        english_title = english_lines[1].strip() if len(english_lines) > 1 else title
        print("Reused the existing English translation.")
    else:
        english_title, english = english_document(
            title,
            body,
            os.environ.get("MYMEMORY_CONTACT_EMAIL", "").strip(),
        )

    write_notice(notice_id, requested_url, title, english_title, korean, english)
    write_output("notice_id", notice_id)
    print(f"Generated UTF-8 Korean and English pages for KISA notice {notice_id}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
