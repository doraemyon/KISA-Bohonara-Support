from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import urllib.parse
import urllib.request

import process_notice

BOARD_URL = "https://www.boho.or.kr/kr/bbs/list.do?bbsId=B0000133&menuNo=205020"
MAX_PAGES = 36


@dataclass(frozen=True)
class Notice:
    notice_id: str
    title: str
    url: str
    published: date
    ordinal: int | None

    def request(self) -> tuple[str, str, str]:
        return self.notice_id, self.title, self.url


def parse_page(html: str) -> list[Notice]:
    parser = process_notice.DocumentParser()
    parser.feed(html)
    entries = []
    for row in process_notice.walk(parser.root):
        if row.tag != "tr":
            continue
        cells = [cell for cell in row.children if isinstance(cell, process_notice.Node) and cell.tag == "td"]
        if len(cells) != 5:
            continue
        number = process_notice.normalize_inline(process_notice.plain_inline(cells[0]))
        if number != "공지" and not number.isdecimal():
            continue
        link = process_notice.first_descendant(cells[1], tag="a")
        if not link:
            raise RuntimeError("The KISA notice list contains a row without a notice link.")
        url, notice_id = process_notice.validate_notice_url(
            urllib.parse.urljoin(BOARD_URL, link.attrs.get("href", ""))
        )
        title = process_notice.normalize_inline(process_notice.plain_inline(link))
        if not title:
            raise RuntimeError("The KISA notice list contains an empty title.")
        published = date.fromisoformat(
            process_notice.normalize_inline(process_notice.plain_inline(cells[-1]))
        )
        entries.append(Notice(notice_id, title, url, published, int(number) if number.isdecimal() else None))
    if not entries:
        raise RuntimeError("No notice rows were found on the official KISA list.")
    return entries


def fetch_page(page: int, *, timeout: int = 12) -> list[Notice]:
    request = urllib.request.Request(
        f"{BOARD_URL}&pageIndex={page}",
        headers={"User-Agent": "kisa-notice-formatter/3.0 (+GitHub Actions)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(process_notice.MAX_PAGE_BYTES + 1)
    if len(body) > process_notice.MAX_PAGE_BYTES:
        raise RuntimeError("The KISA notice list exceeded its size limit.")
    return parse_page(body.decode("utf-8-sig"))


def update_board_numbers(entries: list[Notice]) -> None:
    """Update displayed numbers from the board without changing stable notice IDs."""
    for entry in entries:
        path = process_notice.SITE_ROOT / "notices" / entry.notice_id / "metadata.json"
        if not path.is_file():
            continue
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if "board_number" in metadata and metadata["board_number"] == entry.ordinal:
            continue
        metadata["board_number"] = entry.ordinal
        path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def official_notices(since: date, until: date) -> list[Notice]:
    seen: dict[str, Notice] = {}
    previous: Notice | None = None
    for page in range(1, MAX_PAGES + 1):
        regular_rows = 0
        for entry in fetch_page(page):
            if entry.ordinal is not None:
                regular_rows += 1
                if previous and (
                    entry.ordinal != previous.ordinal - 1 or entry.published > previous.published
                ):
                    raise RuntimeError("KISA pagination changed during the scan. Retry the scan.")
                previous = entry
            if since <= entry.published <= until:
                seen.setdefault(entry.notice_id, entry)
        if not regular_rows:
            raise RuntimeError("The KISA list returned no numbered rows.")
        if previous and previous.published < since:
            return sorted(seen.values(), key=lambda entry: (entry.published, int(entry.notice_id)), reverse=True)
    raise RuntimeError(f"KISA coverage reached the {MAX_PAGES}-page limit before {since}.")
