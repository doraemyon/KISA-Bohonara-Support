#!/usr/bin/env python3
"""Fetch, format, translate, and render one KISA security notice."""

from __future__ import annotations

import asyncio
import html
import os
import re
import sys
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


def translation_batches(lines: list[str]) -> Iterable[list[tuple[int, str]]]:
    batch: list[tuple[int, str]] = []
    characters = 0
    for index, line in enumerate(lines):
        if not line:
            continue
        if len(line) > 14_000:
            fail("A notice line was too long for the translation service.")
        if batch and (len(batch) >= 50 or characters + len(line) > 25_000):
            yield batch
            batch = []
            characters = 0
        batch.append((index, line))
        characters += len(line)
    if batch:
        yield batch


async def translate_with_googletrans(lines: list[str]) -> list[str]:
    try:
        from googletrans import Translator
    except ImportError:
        fail("googletrans is not installed; install requirements.txt first.")

    translated = list(lines)
    async with Translator(service_urls=["translate.googleapis.com"]) as translator:
        for batch in translation_batches(lines):
            values = [line for _, line in batch]
            results = None
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    results = await translator.translate(values, src="ko", dest="en")
                    break
                except Exception as error:
                    last_error = error
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
            if results is None:
                fail(f"Free Google translation failed after three attempts: {last_error}")
            if not isinstance(results, list) or len(results) != len(batch):
                fail("Free Google translation returned an unexpected number of lines.")
            for (index, _), result in zip(batch, results, strict=True):
                text = getattr(result, "text", None)
                if not isinstance(text, str):
                    fail("Free Google translation returned a malformed line.")
                translated[index] = html.unescape(text)
    return translated


def translate_to_english(korean: str) -> str:
    lines = korean.splitlines()
    try:
        translated = asyncio.run(translate_with_googletrans(lines))
    except RuntimeError as error:
        if "asyncio.run() cannot be called" not in str(error):
            raise
        fail("Translation cannot run inside an existing asyncio event loop.")
    return "\n".join(translated).rstrip() + "\n"


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
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
  <main>
    <div class="toolbar">
      <button id="copy-all" type="button">{copy_label}</button>
      <a class="button secondary" href="./notice.txt" download>{download_label}</a>
      <a class="source" href="{html.escape(source_url, quote=True)}" target="_blank" rel="noreferrer">{source_label}</a>
    </div>
    <pre id="notice-text">{html.escape(notice_text.rstrip())}</pre>
  </main>
  <script src="/assets/app.js" defer></script>
</body>
</html>
"""


def write_notice(notice_id: str, source_url: str, title: str, korean: str, english: str) -> None:
    for language, text in (("ko", korean), ("en", english)):
        target = SITE_ROOT / "notices" / notice_id / language
        target.mkdir(parents=True, exist_ok=True)
        (target / "notice.txt").write_text(text, encoding="utf-8", newline="\n")
        (target / "index.html").write_text(
            render_page(language, title, text, source_url),
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
    if cached_ko.exists() and cached_en.exists() and cached_ko.read_text(encoding="utf-8") == korean:
        english = cached_en.read_text(encoding="utf-8")
        print("Reused the existing English translation.")
    else:
        english = translate_to_english(korean)

    write_notice(notice_id, requested_url, title, korean, english)
    write_output("notice_id", notice_id)
    print(f"Generated UTF-8 Korean and English pages for KISA notice {notice_id}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
