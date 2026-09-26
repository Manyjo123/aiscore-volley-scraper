#!/usr/bin/env python3
"""CanlÄ± odds extract debug: odds_for sonucunu ve ham dict'i bas."""
import io, sys, requests, json, ast
import blackboxprotobuf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_log = open("dbg_odds.log", "w", encoding="utf-8")
_orig_print = print


def print(*a, **k):
    _orig_print(*a, **k)
    try:
        _log.write(" ".join(str(x) for x in a) + "\n")
        _log.flush()
    except Exception:
        pass
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


def nested(o):
    if isinstance(o, dict): return {k: nested(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [nested(b2s(v)) for v in o]
    s = b2s(o)
    if s.startswith("{") or s.startswith("["):
        try:
            return nested(ast.literal_eval(s))
        except Exception:
            return s
    return s


def row_val(r, idx):
    try:
        d = r.get("1")
        if isinstance(d, dict):
            d = d.get("1")
        if isinstance(d, list) and len(d) > idx:
            o = str(d[idx])
            if o.replace(".", "").replace(",", "").isdigit():
                return o
    except Exception as e:
        print("  row_val ERR", str(e)[:60])
    return None


def extract_bet365(msg):
    out = {}
    try:
        f15 = msg.get("15")
    except Exception as e:
        print("  f15 ERR", str(e)[:60])
        return out
    if not isinstance(f15, dict):
        print("  f15 dict deÄŸil:", type(f15).__name__, "|", str(f15)[:120])
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
        r_open = m.get("1")
        r_cur = m.get("2") or m.get("4")
        if not (isinstance(r_open, dict) and isinstance(r_cur, dict)):
            print("   row yok")
            continue
        oev, ode = row_val(r_open, 0), row_val(r_open, 2)
        cev, cde = row_val(r_cur, 0), row_val(r_cur, 2)
        print("   r_open:", json.dumps(r_open, ensure_ascii=False)[:60],
              "| r_cur:", json.dumps(r_cur, ensure_ascii=False)[:60])
        print("   oev/ode/cev/cde:", oev, ode, cev, cde)
        out[mname] = {"open": [oev, "0", ode, "0"],
                      "close": [oev, "0", ode, "0"],
                      "current": [cev, "0", cde, "0"],
                      "company": "bet365"}
    return out


for mid in ("vmqylio8meoigk9", "9gkldiwopy0amqx"):
    print("=====", mid)
    r = requests.get(f"{API}/v1/m/api/match/odds/list?match_id={mid}&code=&platform=1", headers=HEADERS, timeout=20)
    print("HTTP", r.status_code, "len", len(r.content))
    if len(r.content) < 100:
        print("  Ã§ok kÄ±sa")
        continue
    try:
        msg = blackboxprotobuf.decode_message(r.content)[0]
    except Exception as e:
        print("  DECODE ERR", str(e)[:100])
        continue
    print("  Ã¼st keys:", list(msg.keys()))
    res = extract_bet365(nested(msg))
    print("  SONUÃ‡:", json.dumps(res, ensure_ascii=False))
