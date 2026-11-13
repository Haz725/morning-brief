#!/usr/bin/env python3
"""brief.py 가 만든 .notify.json 을 ntfy 로 휴대폰에 보낸다."""
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIFY_PATH = os.path.join(ROOT, ".notify.json")


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()  # 붙여넣을 때 섞인 공백 제거
    if not topic:
        sys.exit("NTFY_TOPIC 시크릿이 필요합니다.")
    with open(NOTIFY_PATH, encoding="utf-8") as f:
        n = json.load(f)

    body = {
        "topic": topic,
        "title": n["title"],
        "message": n["message"],
        "tags": n.get("tags", []),
        "priority": 4,
    }
    if os.environ.get("APP_URL"):
        body["click"] = os.environ["APP_URL"]  # 알림을 누르면 앱이 열림

    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    r = requests.post(server, json=body, timeout=15)
    r.raise_for_status()
    print("알림 전송 완료")


if __name__ == "__main__":
    main()
