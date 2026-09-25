#!/usr/bin/env python3
"""aiscore canlı voleybol yapısını keşfet: today/matches içinde status değerleri
ve canlı maçların skor/set bilgileri nerede? live.json üretimi için baz."""
import json, io, sys, requests
import blackboxprotobuf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.aiscore.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
           "Referer": "https://www.aiscore.com/"}
MID = "9gkldi1zyjdimqx"


def b2s(v):
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s


def clean(o):
    if isinstance(o, dict): return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [clean(b2s(v)) for v in o]
    return b2s(o)


def get(name, path):
    try:
        r = requests.get(API + path, headers=HEADERS, timeout=25)
        print(name, "HTTP", r.status_code, "len", len(r.content))
        if len(r.content) < 40:
            return None
        try:
            msg, _ = blackboxprotobuf.decode_message(r.content)
            return clean(msg)
        except Exception as e:
            print(name, "DECODE ERR", str(e)[:120])
            # ham metinde status/score araması
            t = r.content.decode("latin1", "replace")
            for kw in ("status", "score", "live", "pt"):
                i = t.find(kw)
                if i >= 0:
                    print(name, kw, "->", t[i:i + 120])
            return None
    except Exception as e:
        print(name, "ERR", str(e)[:100])
        return None


out = {}
# Bugünkü tüm maçlar (canlı + program)
out["today"] = get("today", "/v1/web/api/today/matches?sid=10&tz=08:00&lang=tr")
# Gelecek
out["future"] = get("future", "/v1/web/api/matches/future?lang=tr&sid=10")
# Canlı (blob)
out["live_blob"] = get("live_blob", "/v1/web/api/live/matches?lang=tr&sport_id=10")

json.dump(out, open("probe_live_struct.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# today içindeki status değerlerini ve skor alanını özetle
if isinstance(out["today"], dict):
    t15 = out["today"].get("15")
    if isinstance(t15, str):
        try:
            import ast
            t15 = ast.literal_eval(t15)
        except Exception as e:
            print("t15 literal_eval ERR", str(e)[:120])
    if isinstance(t15, dict):
        mlist = t15.get("2") or []
        if isinstance(mlist, dict):
            mlist = [mlist]
        print("today: maç sayısı:", len(mlist) if isinstance(mlist, list) else "?")
        statuses = {}
        if isinstance(mlist, list):
            for m in mlist:
                st = m.get("16")
                statuses[str(st)] = statuses.get(str(st), 0) + 1
            print("status dağılımı:", statuses)
            for m in mlist:
                st = m.get("16")
                if str(st) in ("1", "2", "3", "434", "100", "101", "102"):
                    print(" canlı adayı:", json.dumps({k: m.get(k) for k in
                        ("1", "3", "4", "6", "7", "8", "9", "15", "16", "17", "18")},
                        ensure_ascii=False)[:200])
print("kayıt: probe_live_struct.json")