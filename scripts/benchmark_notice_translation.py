from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import process_notice as formatter

CASES = {
    "72132": "General notice on credential exposure",
    "72230": "General PHP notice with prior mistranslation",
    "72284": "Security measures advisory with patch guidance",
    "72302": "Node.js update with previously canceled generation",
    "72295": "SAP update with version and product tables",
}


def archived_translation(notice_id: str, root: Path) -> str:
    if notice_id == "72230":
        return subprocess.check_output(
            ["git", "show", "a613d36:site/notices/72230/en/notice.txt"],
            encoding="utf-8",
        )
    return (root / "en/notice.txt").read_text(encoding="utf-8")


def validation(korean: str, english: str) -> str | None:
    try:
        formatter.validate_english_document(
            korean, formatter.document_title(english, "en"), english
        )
    except RuntimeError as error:
        return str(error)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--notice-ids", default="")
    args = parser.parse_args()
    selected = args.notice_ids.split(",") if args.notice_ids else list(CASES)
    if any(notice_id not in CASES for notice_id in selected):
        parser.error("Unknown notice ID in --notice-ids.")
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    output = Path("benchmark-results")
    output.mkdir(exist_ok=True)
    metrics: list[dict[str, object]] = []
    for index, notice_id in enumerate(selected):
        category = CASES[notice_id]
        root = Path("site/notices") / notice_id
        korean = (root / "ko/notice.txt").read_text(encoding="utf-8")
        title, body = formatter.korean_document_parts(korean)
        if not title or not body:
            raise RuntimeError(f"Could not parse fixture {notice_id}")
        korean = formatter.korean_document(title, body)
        baseline = archived_translation(notice_id, root)
        record: dict[str, object] = {
            "notice_id": notice_id,
            "category": category,
            "update_advisory": formatter.is_update_advisory(title, body),
            "source_characters": len(korean),
            "baseline_validation_error": validation(korean, baseline),
        }
        (output / f"{notice_id}-baseline.txt").write_text(baseline, encoding="utf-8")
        (output / f"{notice_id}-ko.txt").write_text(korean, encoding="utf-8")
        if not args.baseline_only and key:
            if index:
                time.sleep(14)
            start = time.monotonic()
            try:
                translated_title, translated = formatter.translate_with_gemini(korean, key, model)
                _, translated = formatter.finalize_english_document(
                    title, body, translated_title, translated
                )
                record["gemini_validation_error"] = validation(korean, translated)
                (output / f"{notice_id}-gemini.txt").write_text(translated, encoding="utf-8")
            except (OSError, RuntimeError, ValueError) as error:
                record["gemini_validation_error"] = str(error).replace(key, "[REDACTED]")
            record["gemini_seconds"] = round(time.monotonic() - start, 1)
        metrics.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    report = {"model": model, "gemini_attempted": bool(key and not args.baseline_only), "cases": metrics}
    (output / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.baseline_only and not key:
        raise SystemExit("GEMINI_API_KEY is not configured.")


if __name__ == "__main__":
    main()
