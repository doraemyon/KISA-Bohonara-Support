#!/usr/bin/env python3
"""Persist notice requests until both language documents are published."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import process_notice


QUEUE_PATH = Path(__file__).resolve().parents[1] / "data" / "recovery_queue.json"


def load_queue() -> list[tuple[str, str, str]]:
    try:
        payload = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as error:
        process_notice.fail(f"Could not read the recovery queue: {error}")

    raw_notices = payload.get("notices", []) if isinstance(payload, dict) else []
    notices: list[tuple[str, str, str]] = []
    for item in raw_notices:
        if not isinstance(item, dict):
            continue
        notice_id = str(item.get("notice_id", "")).strip()
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        if notice_id.isdigit() and title and url:
            notices.append((notice_id, title, url))
    return notices


def write_queue(notices: list[tuple[str, str, str]]) -> None:
    unique = {notice_id: (notice_id, title, url) for notice_id, title, url in notices}
    payload = {
        "notices": [
            {"notice_id": notice_id, "title": title, "url": url}
            for notice_id, title, url in unique.values()
        ]
    }
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = QUEUE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(QUEUE_PATH)


def add_notice(url: str, title: str) -> str:
    normalized_url, notice_id = process_notice.validate_notice_url(url)
    title = title.strip()
    if not title:
        process_notice.fail("NOTICE_TITLE is required to queue a notice.")
    notices = [item for item in load_queue() if item[0] != notice_id]
    notices.append((notice_id, title, normalized_url))
    write_queue(notices)
    return notice_id


def remove_notice(notice_id: str) -> None:
    notice_id = notice_id.strip()
    if not notice_id.isdigit():
        process_notice.fail("A numeric notice ID is required to update the recovery queue.")
    write_queue([item for item in load_queue() if item[0] != notice_id])


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"add", "remove"}:
        process_notice.fail("Usage: recovery_queue.py add | remove NOTICE_ID")
    if sys.argv[1] == "add":
        notice_id = add_notice(
            process_notice.required_env("NOTICE_URL"),
            process_notice.required_env("NOTICE_TITLE"),
        )
        write_output("notice_id", notice_id)
        write_output("generation_status", "queued")
        print(f"Queued KISA notice {notice_id} for automatic recovery.")
        return

    if len(sys.argv) != 3:
        process_notice.fail("Usage: recovery_queue.py remove NOTICE_ID")
    remove_notice(sys.argv[2])


if __name__ == "__main__":
    main()
