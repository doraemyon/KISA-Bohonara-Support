#!/usr/bin/env python3
"""Add protected Korean and English page buttons to a Telegram message."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def fail(message: str) -> None:
    raise RuntimeError(message)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        fail(f"Required value {name} is empty or missing.")
    return value


def validated_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        fail("PUBLIC_BASE_URL must be an HTTPS URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        fail("PUBLIC_BASE_URL must not contain credentials, a query, or a fragment.")
    return value.rstrip("/")


def main() -> None:
    token = required_env("TELEGRAM_BOT_TOKEN")
    chat_id = required_env("TELEGRAM_CHAT_ID")
    message_id = required_env("TELEGRAM_MESSAGE_ID")
    notice_id = required_env("NOTICE_ID")
    notice_url = required_env("NOTICE_URL")
    base_url = validated_base_url(required_env("PUBLIC_BASE_URL"))
    if not re.fullmatch(r"\d{1,20}", message_id):
        fail("TELEGRAM_MESSAGE_ID must be numeric.")
    if not re.fullmatch(r"\d{1,20}", notice_id):
        fail("NOTICE_ID must be numeric.")

    root = f"{base_url}/notices/{notice_id}"
    payload = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "공지 열기", "url": notice_url}],
                [
                    {"text": "국문 공지", "url": f"{root}/ko/"},
                    {"text": "영문 공지", "url": f"{root}/en/"},
                ],
            ]
        },
    }
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/editMessageReplyMarkup",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "kisa-notice-formatter/1.0 (+GitHub Actions)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        safe_body = error.read().decode("utf-8", errors="replace")[:500]
        if error.code == 400 and "message is not modified" in safe_body.lower():
            print("Telegram buttons were already current.")
            return
        fail(f"Telegram returned HTTP {error.code}: {safe_body}")
    except urllib.error.URLError as error:
        fail(f"Could not reach Telegram: {error.reason}")
    except json.JSONDecodeError:
        fail("Telegram returned invalid JSON.")
    if not isinstance(result, dict) or result.get("ok") is not True:
        fail(f"Telegram rejected the button update: {json.dumps(result, ensure_ascii=False)[:500]}")
    print("Added Korean and English buttons to the Telegram message.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
