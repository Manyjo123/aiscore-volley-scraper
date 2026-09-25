#!/usr/bin/env python3
"""Canlı odds extract debug: odds_for sonucunu ve ham dict'i bas."""
import io, sys, requests, json, ast
import blackboxprotobuf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.aiscore.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
BET365_ID = 2
MARKET_NAMES = {"1": "AH", "2": "1X2", "3": "OU", "5": "OU2"}


def b2s(v):
    if v is None:
        return ""
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s


def clean(o):
    if isinstance(o, dict): return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [clean(b2s(v)) for v in o]
    return b2s(o)


def row_odds(r):
    try:
        d = r.get("1")
        if isinstance(d, dict):
            d = d.get("1")
        if isinstance(d, list) and len(d) >= 3:
            o = str(d[2])
            if o.replace(".", "").replace(",", "").isdigit():
                return o
    except Exception as e:
        print("  row_odds ERR", str(e)[:60])
    return None


def extract_bet365(msg):
    out = {}
    try:
        f15 = msg.get("15")
    except Exception as e:
        print("  f15 ERR", str(e)[:60])
        return out
    if not isinstance(f15, dict):
        print("  f15 dict değil:", type(f15).__name__, "|", str(f15)[:120])
        return out
    print("  f15 keys:", list(f15.keys()))
    for mkey, mname in MARKET_NAMES.items():
        m = f15.get(mkey)
        print("  market", mkey, mname, "tipi:", type(m).__name__, "|", json.dumps(m, ensure_ascii=False)[:200] if m else "None")
        if not isinstance(m, dict):
            continue
        try:
            company = int((m.get("3") or {}).get("1", -1))
        except Exception:
            company = -1
        print("   company:", company, "beklenen:", BET365_ID)
        if company != BET365_ID:
            continue
        row_home = m.get("1")
        row_away = m.get("2")
        cur_home = m.get("4") or row_home
        print("   row_home:", json.dumps(row_home, ensure_ascii=False)[:100] if row_home else None)
        oev, ode, cev = row_odds(row_home), row_odds(row_away), row_odds(cur_home)
        print("   oev/ode/cev:", oev, ode, cev)
        out[mname] = {"open": [oev, "0", ode, "0"],
                      "close": [oev, "0", ode, "0"],
                      "current": [cev, "0", ode, "0"],
                      "company": "bet365"}
    return out


for mid in ("vmqylio8meoigk9", "9gkldiwopy0amqx"):
    print("=====", mid)
    r = requests.get(f"{API}/v1/m/api/match/odds/list?match_id={mid}&code=&platform=1", headers=HEADERS, timeout=20)
    print("HTTP", r.status_code, "len", len(r.content))
    if len(r.content) < 100:
        print("  çok kısa")
        continue
    try:
        msg = blackboxprotobuf.decode_message(r.content)[0]
    except Exception as e:
        print("  DECODE ERR", str(e)[:100])
        continue
    print("  üst keys:", list(msg.keys()))
    res = extract_bet365(clean(msg))
    print("  SONUÇ:", json.dumps(res, ensure_ascii=False))