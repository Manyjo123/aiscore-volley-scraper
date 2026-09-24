#!/usr/bin/env python3
"""HIZLI TEST: dogrudan erisimde hangi API'ler veri donduruyor?"""
import requests, json, datetime
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
API = "https://api.aiscore.com"

def t(label, url, **kw):
    try:
        r = requests.get(url, headers=H, timeout=15, **kw)
        n = len(r.content)
        ok = "DATA" if n > 40 else "EMPTY"
        print(f"{ok:5} {r.status_code} {n:>6}  {label}")
        return r
    except Exception as e:
        print(f"ERR      {label}  {str(e)[:60]}")
        return None

ds = "2025-06-21"
# known-good odds endpoint as sanity
t("odds-list (sanity)", f"{API}/v1/m/api/match/odds/list?match_id=oj7xoimw3zgi47g&code=&platform=1")
# old-format api endpoints (publicly documented aiscore api)
t("old:score", f"http://api.aiscore.com/v1/m/api/score/list?date={ds}&platform=1")
t("old:sport_match", f"http://api.aiscore.com/v1/m/api/match/loadMatchList?type=2&date={ds}&platform=1")
t("old:match_list", f"http://api.aiscore.com/v1/m/api/match/matchList?date={ds}&platform=1")
# try mobile host variants
for host in ["http://api.aiscore.com", "https://api.aiscore.com"]:
    t(f"{host}:result", f"{host}/v1/m/api/result/list?date={ds}&platform=1")
# www mobile api path
t("m:api", f"https://m.aiscore.com/api/v1/m/api/result/list?date={ds}&platform=1")
t("www:api", f"https://www.aiscore.com/api/v1/m/api/result/list?date={ds}&platform=1")
# third-party mirrors of aiscore data
t("aiscore2", f"https://aiscore2.com/api/match/list?date={ds}")