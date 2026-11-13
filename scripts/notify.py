#!/usr/bin/env python3
"""brief.py 가 만든 .notify.json 을 ntfy 로 휴대폰에 보낸다."""
import json
import os
import re
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIFY_PATH = os.path.join(ROOT, ".notify.json")


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()  # 붙여넣을 때 섞인 공백 제거
    if not topic:
        sys.exit("NTFY_TOPIC 시크릿이 필요합니다.")
    if not re.fullmatch(r"[-_A-Za-z0-9]{1,64}", topic):
        # 토픽 값은 로그에 남기지 않고 무엇이 문제인지만 알려준다
        bad = sorted({"공백" if c.isspace() else ("한글" if "가" <= c <= "힣" else "기타 기호")
                      for c in topic if not re.fullmatch(r"[-_A-Za-z0-9]", c)})
        sys.exit(f"NTFY_TOPIC 은 영문, 숫자, -, _ 만 쓸 수 있어요 (길이 {len(topic)}자, 포함된 문자: {', '.join(bad) or '없음'})")
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
    if r.status_code >= 400:
        sys.exit(f"ntfy 전송 실패 {r.status_code}: {r.text[:300].replace(topic, '***')}")
    print("알림 전송 완료")


if __name__ == "__main__":
    main()
