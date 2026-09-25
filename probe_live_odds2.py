#!/usr/bin/env python3
"""Canlı maç odds/list yapısını detaylı bas."""
import io, sys, requests, json
import blackboxprotobuf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.aiscore.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
MID = "9gkldiwopy0amqx"


def b2s(v):
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    return v


def clean(o):
    if isinstance(o, dict): return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [clean(b2s(v)) for v in o]
    return b2s(o)


r = requests.get(f"{API}/v1/m/api/match/odds/list?match_id={MID}&code=&platform=1", headers=HEADERS, timeout=20)
print("HTTP", r.status_code, "len", len(r.content))
msg, _ = blackboxprotobuf.decode_message(r.content)
msg = clean(msg)
f15 = msg.get("15")
if isinstance(f15, dict):
    for k in ("1", "2", "3", "4", "5", "8"):
        v = f15.get(k)
        print(f"-- market {k}: {json.dumps(v, ensure_ascii=False)[:600]}" if v is not None else f"-- market {k}: yok")