#!/usr/bin/env python3
"""
매일 아침 실행되는 메인 스크립트.

1) 09:01(KST)까지 기다렸다가 네이버 금융에서 현재가 조회
2) 계좌별 수익률, 평단, 평가금액 계산
3) 간밤 미국 지수/주요 종목/환율(네이버, 실패 시 야후)과 구글 뉴스 RSS 수집 (모두 무료, 키 없음)
4) 결과를 비밀번호로 암호화해서 docs/data.enc.json 에 저장 (앱이 이걸 읽음)
5) 휴대폰 알림 내용을 .notify.json 에 저장 (notify.py 가 전송)
"""
import base64
import datetime as dt
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

KST = ZoneInfo("Asia/Seoul")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "docs", "data.enc.json")
NOTIFY_PATH = os.path.join(ROOT, ".notify.json")
LOCAL_HOLDINGS = os.path.join(ROOT, "holdings.json")

PBKDF2_ITER = 250_000
HISTORY_DAYS = 120
UA = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-S921N) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
}


# ───────────────────────── 암호화 ─────────────────────────
def _key(password: str, salt: bytes, iterations: int = PBKDF2_ITER) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(password.encode("utf-8"))


def encrypt(obj, password: str) -> dict:
    salt, iv = os.urandom(16), os.urandom(12)
    plain = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    ct = AESGCM(_key(password, salt)).encrypt(iv, plain, None)
    b64 = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "iter": PBKDF2_ITER, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}


def decrypt(blob: dict, password: str):
    d = lambda k: base64.b64decode(blob[k])
    key = _key(password, d("salt"), blob.get("iter", PBKDF2_ITER))
    return json.loads(AESGCM(key).decrypt(d("iv"), d("ct"), None))


# ───────────────────────── 설정 읽기 ─────────────────────────
def load_holdings() -> dict:
    raw = os.environ.get("HOLDINGS_JSON")
    if raw:
        return json.loads(raw)
    if os.path.exists(LOCAL_HOLDINGS):
        with open(LOCAL_HOLDINGS, encoding="utf-8") as f:
            return json.load(f)
    sys.exit("보유 종목 정보가 없습니다. HOLDINGS_JSON 시크릿을 설정하거나 holdings.json 을 만드세요.")


def load_history(password: str) -> list:
    if not os.path.exists(DATA_PATH):
        return []
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            return decrypt(json.load(f), password).get("history", [])
    except Exception as e:  # 비밀번호를 바꾼 경우 등
        print(f"[경고] 이전 기록을 읽지 못해 새로 시작합니다: {e}")
        return []


# ───────────────────────── 시세 조회 ─────────────────────────
def _num(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(",", "").replace("+", "").strip() or 0)


def _signed(value: float, direction) -> float:
    """네이버는 전일대비를 부호 없이 줄 때가 있어서 방향 코드로 부호를 맞춘다."""
    name = ""
    if isinstance(direction, dict):
        name = f"{direction.get('name', '')}{direction.get('code', '')}".upper()
    if any(k in name for k in ("FALL", "LOWER", "4", "5")):
        return -abs(value)
    if any(k in name for k in ("RIS", "UPPER", "1", "2")):
        return abs(value)
    return value


def fetch_price(code: str) -> dict:
    errors = []
    urls = [
        f"https://m.stock.naver.com/api/stock/{code}/basic",
        f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=UA, timeout=10)
            r.raise_for_status()
            d = r.json()
            if "datas" in d:
                d = d["datas"][0]
            price = _num(d["closePrice"])
            change = _signed(_num(d.get("compareToPreviousClosePrice", 0)),
                             d.get("compareToPreviousPrice"))
            prev = price - change
            return {
                "price": price,
                "change": change,
                "change_pct": round(change / prev * 100, 2) if prev else 0.0,
                "market_status": d.get("marketStatus", ""),
            }
        except Exception as e:
            errors.append(f"{url}: {e}")
    raise RuntimeError(" / ".join(errors))


def build_portfolio(cfg: dict) -> dict:
    cache = {}
    accounts, statuses = [], set()
    t_cost = t_value = t_day = 0.0
    for acc in cfg["accounts"]:
        a_cost = a_value = a_day = 0.0
        rows = []
        for h in acc["holdings"]:
            code, qty, avg = str(h["code"]).zfill(6), float(h["qty"]), float(h["avg"])
            row = {"name": h["name"], "code": code, "qty": qty, "avg": avg}
            try:
                if code not in cache:
                    cache[code] = fetch_price(code)
                q = cache[code]
                statuses.add(q["market_status"])
                cost, value = qty * avg, qty * q["price"]
                row.update(price=q["price"], value=value, cost=cost, pnl=value - cost,
                           pnl_pct=(value / cost - 1) * 100 if cost else 0,
                           day_change=qty * q["change"], day_change_pct=q["change_pct"])
                a_cost += cost
                a_value += value
                a_day += qty * q["change"]
            except Exception as e:
                print(f"[경고] {h['name']}({code}) 시세 조회 실패: {e}")
                row["error"] = "시세를 가져오지 못했어요"
            rows.append(row)
        accounts.append({
            "name": acc["name"], "holdings": rows, "cost": a_cost, "value": a_value,
            "pnl": a_value - a_cost, "pnl_pct": (a_value / a_cost - 1) * 100 if a_cost else 0,
            "day_change": a_day,
            "day_change_pct": a_day / (a_value - a_day) * 100 if a_value - a_day else 0,
        })
        t_cost += a_cost
        t_value += a_value
        t_day += a_day
    prev_value = t_value - t_day
    return {
        "accounts": accounts, "cost": t_cost, "value": t_value, "pnl": t_value - t_cost,
        "pnl_pct": (t_value / t_cost - 1) * 100 if t_cost else 0,
        "day_change": t_day, "day_change_pct": t_day / prev_value * 100 if prev_value else 0,
        "market_status": "CLOSE" if statuses == {"CLOSE"} else ("OPEN" if "OPEN" in statuses else ""),
    }


# ───────────────────────── 간밤 시장 (무료, 키 없음) ─────────────────────────
# (표시 이름, 네이버 코드, 야후 심볼) — 네이버 실패 시 야후 chart API 로 재시도
INDICES = [
    ("나스닥100", "index/.NDX", "^NDX"),
    ("필라델피아 반도체(SOX)", "index/.SOX", "^SOX"),
    ("S&P500", "index/.INX", "^GSPC"),
]
STOCKS = [
    ("엔비디아", "stock/NVDA.O", "NVDA"),
    ("브로드컴", "stock/AVGO.O", "AVGO"),
    ("AMD", "stock/AMD.O", "AMD"),
    ("TSMC(ADR)", "stock/TSM", "TSM"),
    ("애플", "stock/AAPL.O", "AAPL"),
    ("마이크로소프트", "stock/MSFT.O", "MSFT"),
]
NEWS_QUERIES = ["나스닥", "필라델피아 반도체", "엔비디아", "미국 증시", "뉴욕증시"]
NEWS_MAX = 15


def _quote_naver(path: str) -> dict:
    r = requests.get(f"https://api.stock.naver.com/{path}/basic", headers=UA, timeout=10)
    r.raise_for_status()
    d = r.json()
    return {"price": _num(d["closePrice"]), "change": _num(d["compareToPreviousClosePrice"]),
            "change_pct": _num(d["fluctuationsRatio"]), "traded_at": d.get("localTradedAt", "")}


def _quote_yahoo(symbol: str) -> dict:
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"range": "5d", "interval": "1d"},
                     headers={"User-Agent": UA["User-Agent"]}, timeout=10)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    price, prev = closes[-1], closes[-2]
    ts = dt.datetime.fromtimestamp(res["timestamp"][-1], dt.timezone.utc)
    return {"price": round(price, 2), "change": round(price - prev, 2),
            "change_pct": round((price / prev - 1) * 100, 2), "traded_at": ts.isoformat()}


def fetch_quote(name: str, naver: str, yahoo: str) -> dict:
    errors = []
    for fn, arg in ((_quote_naver, naver), (_quote_yahoo, yahoo)):
        try:
            return {"name": name, **fn(arg)}
        except Exception as e:
            errors.append(f"{fn.__name__}: {e}")
    print(f"[경고] {name} 시세 조회 실패: {' / '.join(errors)}")
    return {"name": name, "error": "가져오지 못했어요"}


def fetch_fx() -> dict:
    """원/달러 환율 (네이버, 하나은행 고시 기준). 실패하면 야후 KRW=X."""
    try:
        r = requests.get("https://api.stock.naver.com/marketindex/exchange/FX_USDKRW",
                         headers=UA, timeout=10)
        r.raise_for_status()
        d = r.json()["exchangeInfo"]
        return {"price": _num(d["closePrice"]), "change": _num(d["fluctuations"]),
                "change_pct": _num(d["fluctuationsRatio"]), "traded_at": d.get("localTradedAt", "")}
    except Exception as e:
        print(f"[경고] 네이버 환율 조회 실패, 야후로 재시도: {e}")
    try:
        return _quote_yahoo("KRW=X")
    except Exception as e:
        print(f"[경고] 야후 환율 조회 실패: {e}")
        return {"error": "가져오지 못했어요"}


def fetch_news(now: dt.datetime) -> list:
    """구글 뉴스 RSS(한국어)에서 최근 24시간 기사. 링크/제목 중복 제거,
    한 키워드가 몰리지 않게 키워드별로 번갈아 뽑은 뒤 최신순."""
    since = now - dt.timedelta(hours=24)
    per_query, seen = [], set()
    for q in NEWS_QUERIES:
        items = []
        per_query.append(items)
        try:
            r = requests.get("https://news.google.com/rss/search",
                             params={"q": f"{q} when:1d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                             headers={"User-Agent": UA["User-Agent"]}, timeout=10)
            r.raise_for_status()
            for it in ET.fromstring(r.content).iter("item"):
                title, link = it.findtext("title", "").strip(), it.findtext("link", "").strip()
                source = it.findtext("source", "").strip()
                if source and title.endswith(f" - {source}"):
                    title = title[: -len(source) - 3].strip()
                try:
                    published = parsedate_to_datetime(it.findtext("pubDate", ""))
                except (TypeError, ValueError):
                    continue
                key = re.sub(r"\W", "", title)
                if not title or published < since or link in seen or key in seen:
                    continue
                seen.update((link, key))
                items.append({"title": title, "source": source, "url": link,
                              "published": published.astimezone(KST).isoformat(timespec="minutes")})
        except Exception as e:
            print(f"[경고] 뉴스 '{q}' 조회 실패: {e}")
    picked = []
    for group in per_query:
        group.sort(key=lambda x: x["published"], reverse=True)
    while len(picked) < NEWS_MAX and any(per_query):
        for group in per_query:
            if group and len(picked) < NEWS_MAX:
                picked.append(group.pop(0))
    picked.sort(key=lambda x: x["published"], reverse=True)
    return picked


def collect_market() -> dict:
    return {
        "indices": [fetch_quote(*i) for i in INDICES],
        "stocks": [fetch_quote(*s) for s in STOCKS],
        "fx": fetch_fx(),
    }


def market_line(market: dict, short: bool = False) -> str:
    """'간밤 나스닥100 -0.30% · SOX -0.54%' 같은 한 줄 요약."""
    parts = []
    for q in market.get("indices", [])[:2]:
        if "change_pct" in q:
            name = "SOX" if short and "SOX" in q["name"] else q["name"]
            parts.append(f"{name} {q['change_pct']:+.2f}%")
    if not short:
        fx = market.get("fx") or {}
        if "price" in fx:
            parts.append(f"원/달러 {fx['price']:,.1f}원({fx['change']:+.1f})")
    return ("간밤 " + " · ".join(parts)) if parts else ""


# ───────────────────────── 실행 흐름 ─────────────────────────
def wait_for_open():
    """장 시작(09:01) 전이면 기다린다. 너무 이르면(30분 이상) 기다리지 않음."""
    if os.environ.get("NO_WAIT") == "1":
        return
    now = dt.datetime.now(KST)
    target = now.replace(hour=9, minute=1, second=0, microsecond=0)
    gap = (target - now).total_seconds()
    if 0 < gap <= 30 * 60:
        print(f"장 시작까지 {int(gap)}초 대기합니다…")
        time.sleep(gap)


def won(v: float) -> str:
    sign = "+" if v > 0 else ("-" if v < 0 else "")
    v = abs(v)
    if v >= 1e8:
        return f"{sign}{v / 1e8:.2f}억원"
    if v >= 1e4:
        return f"{sign}{v / 1e4:,.0f}만원"
    return f"{sign}{v:,.0f}원"


def build_notification(pf: dict, market: dict, show_amounts: bool) -> dict:
    title = f"내 수익률 {pf['pnl_pct']:+.2f}%  (오늘 {pf['day_change_pct']:+.2f}%)"
    lines = []
    if show_amounts:
        lines.append(f"평가 {won(pf['value']).lstrip('+')}, 손익 {won(pf['pnl'])}")
    for a in pf["accounts"]:
        lines.append(f"{a['name']} {a['pnl_pct']:+.2f}%  (오늘 {a['day_change_pct']:+.2f}%)")
    if pf.get("market_status") == "CLOSE":
        lines.append("오늘은 휴장일이라 전 거래일 종가 기준이에요")
    if market_line(market, short=True):
        lines.append(market_line(market, short=True))
    up = pf["pnl_pct"] >= 0
    return {
        "title": title,
        "message": "\n".join(lines),
        "tags": ["chart_with_upwards_trend" if up else "chart_with_downwards_trend"],
    }


def main():
    password = os.environ.get("APP_PASSWORD")
    if not password:
        sys.exit("APP_PASSWORD 시크릿이 필요합니다.")
    cfg = load_holdings()

    # 1) 09:01 이후 현재가 조회 (환율도 그날 첫 고시가 반영되도록 장 시작 후에 수집)
    wait_for_open()
    now = dt.datetime.now(KST)
    pf = build_portfolio(cfg)

    # 2) 간밤 미국장, 환율, 뉴스 (각 항목이 실패해도 나머지는 계속)
    market = collect_market()
    market["headline"] = market_line(market)
    news = fetch_news(now)

    # 3) 수익률 기록 (같은 날짜는 덮어씀)
    today = now.strftime("%Y-%m-%d")
    history = [h for h in load_history(password) if h.get("date") != today]
    history.append({"date": today, "value": round(pf["value"]), "pnl_pct": round(pf["pnl_pct"], 3)})
    history = history[-HISTORY_DAYS:]

    data = {
        "generated_at": now.isoformat(timespec="seconds"),
        "portfolio": pf,
        "market": market,
        "news": news,
        "history": history,
    }
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(encrypt(data, password), f)

    show_amounts = os.environ.get("NOTIFY_AMOUNTS", "true").lower() != "false"
    with open(NOTIFY_PATH, "w", encoding="utf-8") as f:
        json.dump(build_notification(pf, market, show_amounts), f, ensure_ascii=False)

    print(f"완료: 전체 {pf['pnl_pct']:+.2f}%, 평가 {pf['value']:,.0f}원")


if __name__ == "__main__":
    main()
