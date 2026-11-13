#!/usr/bin/env python3
"""Refresh attachment links for stored notices without retranslating them."""

from __future__ import annotations

import json
import sys

import process_notice


def main() -> None:
    notices_root = process_notice.SITE_ROOT / "notices"
    checked = 0
    with_files = 0
    failed = 0
    for metadata_path in sorted(notices_root.glob("*/metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if "attachments" not in metadata:
            try:
                url, notice_id = process_notice.validate_notice_url(metadata["source_url"])
                if notice_id != metadata_path.parent.name:
                    raise RuntimeError("KISA source URL does not match the stored notice ID.")
                metadata["attachments"] = process_notice.fetch_notice(url).attachments
            except (KeyError, OSError, RuntimeError, ValueError) as error:
                print(f"WARNING: Could not check {metadata_path.parent.name}: {error}", file=sys.stderr)
                failed += 1
                continue
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        if process_notice.stored_attachments(metadata):
            with_files += 1
            process_notice.render_stored_notice_pages(metadata_path.parent, metadata)
        checked += 1

    process_notice.write_notice_index()
    print(f"Checked {checked} notices: {with_files} with attachments, {failed} unavailable.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
