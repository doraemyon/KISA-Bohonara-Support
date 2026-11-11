#!/usr/bin/env python3
"""Retry notices whose Korean page was published before English translation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import process_notice


def pending_metadata(root: Path) -> list[Path]:
    pending: list[Path] = []
    for metadata_path in sorted(root.glob("*/metadata.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"WARNING: Skipping unreadable metadata {metadata_path}: {error}", file=sys.stderr)
            continue
        if metadata.get("translation_status") == "pending":
            pending.append(metadata_path)
    return pending


def main() -> None:
    paths = pending_metadata(process_notice.SITE_ROOT / "notices")
    if not paths:
        print("No pending English translations.")
        return

    completed = 0
    for metadata_path in paths:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        notice_id = str(metadata.get("notice_id", metadata_path.parent.name))
        source_url = str(metadata.get("source_url", "")).strip()
        title = str(metadata.get("title", "")).strip()
        if not source_url or not title:
            print(
                f"WARNING: Notice {notice_id} has incomplete retry metadata; leaving it pending.",
                file=sys.stderr,
            )
            continue

        print(f"Retrying English translation for KISA notice {notice_id}.")
        os.environ["NOTICE_URL"] = source_url
        os.environ["NOTICE_TITLE"] = title
        try:
            process_notice.main()
        except Exception as error:
            print(
                f"WARNING: Retry for KISA notice {notice_id} could not run: {error}",
                file=sys.stderr,
            )
            continue

        refreshed = json.loads(metadata_path.read_text(encoding="utf-8"))
        if refreshed.get("translation_status") == "complete":
            completed += 1

    print(f"Retried {len(paths)} pending translation(s); completed {completed}.")


if __name__ == "__main__":
    main()
