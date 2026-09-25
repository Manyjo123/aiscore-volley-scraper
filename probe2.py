#!/usr/bin/env python3
"""PROBE2: HTML SSR erisilebilir mi + hangi URL date listesi veriyor?"""
import requests, re, json, datetime
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
     "Accept-Language": "en,en-US;q=0.9"}

def t(label, url, **kw):
    try:
        r = requests.get(url, headers=H, timeout=20, **kw)
        body = r.text
        mids = set(re.findall(r'/volleyball/match-[^"<>?]+/([a-z0-9]{15})', body))
        has_nuxt = "__NUXT__" in body
        has_cf = "Just a moment" in body or "cf-chl" in body
        print(f"[{r.status_code}] len={len(body):>8} nuxt={has_nuxt} cf={has_cf} matchids={len(mids)}  {label}")
        return body, mids
    except Exception as e:
        print(f"ERR  {label} {str(e)[:60]}")
        return "", set()

# 1) today's volleyball score pages (server rendered)
b1, _ = t("www /volleyball", "https://www.aiscore.com/volleyball")
b2, _ = t("www /volleyball/score", "https://www.aiscore.com/volleyball/score")
b3, _ = t("www /score", "https://www.aiscore.com/score")
b4, _ = t("m /volleyball", "https://m.aiscore.com/volleyball")
b5, _ = t("m /volleyball/score", "https://m.aiscore.com/volleyball/score")
# 2) dated score pages
ds = "2025-06-21"
for u in ["https://www.aiscore.com/volleyball/score/" + ds,
          "https://www.aiscore.com/volleyball/score?date=" + ds,
          "https://www.aiscore.com/volleyball/" + ds,
          "https://m.aiscore.com/volleyball/score/" + ds,
          "https://m.aiscore.com/volleyball/score?date=" + ds]:
    _, mids = t(u[:60], u)
    if mids:
        print("   >>> DATE PAGE HAS:", list(mids)[:5])
# 3) static.aiscore.com JS reachable?
t("static _nuxt", "https://static.aiscore.com/_nuxt/9bfac20.js")
# 4) dump NUXT shape from one page
for name, body in [("www", b1), ("wwwscore", b2), ("m", b4), ("mscore", b5)]:
    if "__NUXT__" in body:
        m = re.search(r'window\.__NUXT__=(.*?)</script>', body, re.S)
        if m:
            s = m.group(1)
            open(f"/tmp/nuxt_{name}.json", "w", encoding="utf-8").write(s)
            print(f"  saved nuxt_{name}.json len={len(s)}")
            # peek for match-ish keys
            print("   keys:", sorted(set(re.findall(r'"([a-zA-Z_]{6,25})":', s)))[:40])
        break