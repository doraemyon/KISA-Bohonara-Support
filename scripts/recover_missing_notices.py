#!/usr/bin/env python3
"""Recover recent RSS notices that do not yet have both published documents."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import process_notice


RSS_URL = "https://www.boho.or.kr/kr/rss.do?bbsId=B0000133"


def recent_notices() -> list[tuple[str, str, str]]:
    request = urllib.request.Request(
        RSS_URL,
        headers={"User-Agent": "kisa-notice-formatter/3.0 (+GitHub Actions)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, ET.ParseError) as error:
        print(f"WARNING: Could not read the KISA RSS feed: {error}", file=sys.stderr)
        return []

    notices: list[tuple[str, str, str]] = []
    for item in root.findall(".//item")[:30]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        try:
            _url, notice_id = process_notice.validate_notice_url(link)
        except RuntimeError as error:
            print(f"WARNING: Skipping an invalid RSS item: {error}", file=sys.stderr)
            continue
        if title:
            notices.append((notice_id, title, link))
    return notices


def is_complete(notice_id: str) -> bool:
    root = process_notice.SITE_ROOT / "notices" / notice_id
    if not (root / "ko" / "notice.txt").exists() or not (root / "en" / "notice.txt").exists():
        return False
    try:
        metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return metadata.get("translation_status", "complete") == "complete"


def main() -> None:
    missing = [notice for notice in recent_notices() if not is_complete(notice[0])]
    if not missing:
        print("No recent KISA notices need recovery.")
        return

    os.environ.pop("GITHUB_OUTPUT", None)
    recovered = 0
    for notice_id, title, link in reversed(missing):
        print(f"Recovering KISA notice {notice_id}: {title}")
        os.environ["NOTICE_URL"] = link
        os.environ["NOTICE_TITLE"] = title
        try:
            process_notice.main()
            recovered += 1
        except Exception as error:
            print(
                f"WARNING: Notice {notice_id} is still unavailable and will be retried: {error}",
                file=sys.stderr,
            )

    print(f"Recovered {recovered} of {len(missing)} missing notice(s).")


if __name__ == "__main__":
    main()
