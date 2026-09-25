#!/usr/bin/env python3
"""Web API tabanli skor/set-skoru testi: hangi endpoint vbScores + pt + set p1..p5
veriyor? Bilinen skorlu bir macla dogrula (9gkldi1zyjdimqx = 2024-11-25 3-1).
Sonuclari probe_scores.json + canli cikti."""
import json, io, sys, requests, re
import blackboxprotobuf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.aiscore.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
           "Referer": "https://www.aiscore.com/"}
MID = "9gkldi1zyjdimqx"   # 2024-11-25 3-1 (setler 23/25 25/23 25/16 25/21, total 98-85)


def b2s(v):
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s


def clean(o):
    if isinstance(o, dict): return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [clean(b2s(v)) for v in o]
    return b2s(o)


def probe(name, path):
    try:
        r = requests.get(API + path, headers=HEADERS, timeout=25)
        size = len(r.content)
        if size < 20:
            print(f"{name}: {r.status_code} {size}B (bos)")
            return None
        try:
            msg, _ = blackboxprotobuf.decode_message(r.content)
            msg = clean(msg)
            s = json.dumps(msg, ensure_ascii=False)
            print(f"{name}: {r.status_code} {size}B decoded")
            return msg
        except Exception as e:
            # regex ile vbScores arama (ham)
            t = r.content.decode("latin1", "replace")
            hit = re.findall(r'vbScores.{0,200}', t)[:2]
            print(f"{name}: {r.status_code} {size}B PARSE-ERR {str(e)[:80]} | vbScores:{bool(hit)}")
            return None
    except Exception as e:
        print(f"{name}: ERR {str(e)[:100]}")
        return None


out = {}
for name, path in {
    "data":  f"/v1/web/api/match/data?lang=tr&match_id={MID}",
    "tot":   f"/v1/web/api/match/total?match_id={MID}",
    "stat":  f"/v1/web/api/match/stats?match_id={MID}",
    "score": f"/v1/web/api/match/scorecards?match_id={MID}",
    "hist":  f"/v1/web/api/match/history?match_id={MID}",
    "mlive": f"/v1/web/api/match/mlive?lang=tr&match_id={MID}",
    "today201124": "/v1/web/api/matches?lang=tr&sport_id=10&date=2024-11-25",
    "pred": "/v1/web/api/prediction/matches?sport_id=10&lang=tr",
    "dbcomp": "/v1/web/api/database/competition/matches?lang=tr&sid=10&date=2024-11-25",
}.items():
    out[name] = probe(name, path)

json.dump(out, open("probe_scores.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("kayit: probe_scores.json")