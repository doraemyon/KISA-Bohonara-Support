#!/usr/bin/env python3
"""Reconcile the official notice list with the bilingual archive."""

from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import notice_catalog
import process_notice
import recovery_queue


RSS_URL = "https://www.boho.or.kr/kr/rss.do?bbsId=B0000133"
KOREA = timezone(timedelta(hours=9))
NOTICE_TIMEOUT = 120
RUN_BUDGET = 18 * 60


def three_months_before(day: date) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 - 3, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


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
    try:
        for language in ("ko", "en"):
            for filename in ("index.html", "notice.txt"):
                if (root / language / filename).stat().st_size == 0:
                    return False
        metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        metadata.get("notice_id") == notice_id
        and metadata.get("translation_status", "complete") == "complete"
    )


def reconcile(full_scan: bool) -> list[tuple[str, str, str]]:
    today = datetime.now(KOREA).date()
    since = three_months_before(today) if full_scan else today - timedelta(days=14)
    try:
        catalog = notice_catalog.official_notices(since, today)
        discovered = [entry.request() for entry in catalog]
    except (OSError, RuntimeError, ValueError) as error:
        print(f"::warning::Official KISA list scan failed: {error}. Trying RSS and the saved queue.")
        discovered = recent_notices()

    queued = recovery_queue.load_queue()
    previously_queued = {notice[0] for notice in queued}
    new_requests = [notice for notice in discovered if notice[0] not in previously_queued]
    candidates = {notice[0]: notice for notice in new_requests + queued}
    missing = [notice for notice in candidates.values() if not is_complete(notice[0])]
    recovery_queue.write_queue(missing)
    # Repair an index that is stale even when all document files are present.
    if discovered:
        process_notice.write_notice_index()
    return missing


def main(
    *, full_scan: bool = False, limit: int = 12,
    discover_only: bool = False, queued_only: bool = False,
) -> None:
    missing = recovery_queue.load_queue() if queued_only else reconcile(full_scan)
    if discover_only:
        recovery_queue.write_output("pending", str(len(missing)))
        print(f"Discovered {len(missing)} pending KISA notice(s).")
        return
    if not missing:
        print("No KISA notices need recovery.")
        return

    deadline = time.monotonic() + RUN_BUDGET
    env = {key: value for key, value in os.environ.items() if key != "GITHUB_OUTPUT"}
    recovered = 0
    attempted = 0
    for notice_id, title, link in missing[:limit]:
        remaining = deadline - time.monotonic()
        if remaining < 10:
            break
        attempted += 1
        print(f"Recovering KISA notice {notice_id}: {title}")
        try:
            subprocess.run(
                [sys.executable, str(Path(process_notice.__file__).resolve())],
                env={**env, "NOTICE_URL": link, "NOTICE_TITLE": title},
                timeout=min(NOTICE_TIMEOUT, remaining),
                check=True,
            )
            if not is_complete(notice_id):
                raise RuntimeError("The complete bilingual files were not written.")
            recovery_queue.remove_notice(notice_id)
            recovered += 1
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            # Re-adding an item moves it behind untried requests.
            recovery_queue.add_notice(link, title)
            print(
                f"::warning::Notice {notice_id} is still queued for recovery: {error}",
                file=sys.stderr,
            )

    pending = len(recovery_queue.load_queue())
    report = f"Recovered {recovered}/{attempted} attempted notice(s); {pending} remain queued."
    print(report)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as output:
            output.write(report + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-scan", action="store_true")
    parser.add_argument("--limit", type=int, choices=range(1, 121), default=12, metavar="1..120")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--discover-only", action="store_true")
    mode.add_argument("--queued-only", action="store_true")
    args = parser.parse_args()
    main(
        full_scan=args.full_scan, limit=args.limit,
        discover_only=args.discover_only, queued_only=args.queued_only,
    )
