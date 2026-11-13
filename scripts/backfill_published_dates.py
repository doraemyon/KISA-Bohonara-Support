#!/usr/bin/env python3
"""Populate missing KISA publication dates and re-render stored pages."""

from __future__ import annotations

import json
import sys

import process_notice


def main() -> None:
    notices_root = process_notice.SITE_ROOT / "notices"
    updated = 0
    for metadata_path in sorted(notices_root.glob("*/metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("published_date"):
            continue
        source_url = str(metadata.get("source_url", "")).strip()
        if not source_url:
            print(f"WARNING: {metadata_path} has no source URL.", file=sys.stderr)
            continue
        published_date = process_notice.fetch_notice(source_url).published_date
        metadata["published_date"] = published_date
        metadata["format_version"] = process_notice.FORMAT_VERSION
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        updated += 1
        print(f"Stored {published_date} for notice {metadata_path.parent.name}.")

    process_notice.refresh_stored_notice_pages()
    process_notice.write_notice_index()
    print(f"Updated {updated} notice publication date(s).")


if __name__ == "__main__":
    main()
