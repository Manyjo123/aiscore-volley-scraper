#!/usr/bin/env python3
"""Bugun + gelecek voleybol maclarinin bet365 acilis oranlarini
/v1/web/api/today/matches (sid=10) ve /matches/future uzerinden ceker,
upcoming.json uretir. App'in gunluk veri kaynagi."""
import json, time, datetime, ast, re
import requests
import blackboxprotobuf

API = "https://api.aiscore.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
BET365_ID = 2
MARKET_NAMES = {"1": "AH", "2": "1X2", "3": "OU", "5": "OU2"}


def b2s(v):
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s


def fix(o, _top=True):
    """blackbox her zaman tutarli decode etmiyor: bazi field'lar 'str(dict)' olarak
    doner. Bunlari ast.literal_eval ile gercek objeye cevir."""
    if isinstance(o, str):
        s = o.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                return fix(ast.literal_eval(s), _top=False)
            except Exception as e:
                if _top:
                    print("  literal_eval HATA:", str(e)[:200])
                    print("  ornek:", s[:150])
                # fallback: bytes literal'larini (b'...') string'e cevir, tekrar dene
                fixed = re.sub(r"b'((?:[^'\\]|\\.)*)'", lambda m: "'" + m.group(1) + "'", s)
                fixed = fixed.replace("'", '"')
                try:
                    return fix(json.loads(fixed), _top=False)
                except Exception:
                    pass
        return o
    if isinstance(o, list): return [fix(x, _top=False) for x in o]
    if isinstance(o, dict): return {k: fix(v, _top=False) for k, v in o.items()}
    return o


def clean(o):
    if isinstance(o, dict): return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [clean(b2s(v)) for v in o]
    return b2s(o)


MID_RE = re.compile(r"[a-z0-9]{15}")


def get_json(name, path):
    url = API + path
    r = requests.get(url, headers=HEADERS, timeout=20)
    try:
        msg, _ = blackboxprotobuf.decode_message(r.content)
        return clean(fix(msg))
    except Exception as e:
        mids = MID_RE.findall(r.content.decode("latin1", "replace"))
        print(name, "DECODE ERR (fallback)", str(e)[:120], "| regex mids:", len(set(mids)))
        return {"15": {"2": [{"1": m} for m in sorted(set(mids))]}}


def extract_bet365(msg):
    out = {}
    try: f15 = msg.get("15", {})
    except Exception: return out
    for mkey, mname in MARKET_NAMES.items():
        entries = f15.get(mkey, [])
        if isinstance(entries, dict): entries = [entries]
        if not isinstance(entries, list): continue
        for e in entries:
            try: cid = int(e.get("3", {}).get("1", -1))
            except Exception: continue
            if cid != BET365_ID: continue
            o = e.get("1", {}).get("1", []); c = e.get("2", {}).get("1", [])
            cur = e.get("4", {}).get("1", [])
            out[mname] = {"open": [b2s(x) for x in o] if isinstance(o, list) else [],
                          "close": [b2s(x) for x in c] if isinstance(c, list) else [],
                          "current": [b2s(x) for x in cur] if isinstance(cur, list) else [],
                          "company": "bet365"}
    return out


def odds_for(mid):
    r = requests.get(f"{API}/v1/m/api/match/odds/list?match_id={mid}&code=&platform=1",
                     headers=HEADERS, timeout=20)
    if len(r.content) < 100: return {}
    return extract_bet365(clean(blackboxprotobuf.decode_message(r.content)[0]))


def main():
    today = get_json("today", "/v1/web/api/today/matches?sid=10&tz=08:00&lang=tr")
    future = get_json("future", "/v1/web/api/matches/future?lang=tr&sid=10")

    teams, mlist = {}, {}
    for src in (today, future):
        if not isinstance(src, dict):
            continue
        t15 = src.get("15")
        if isinstance(t15, str):
            print("  t15 str ozet:", t15[:400].replace(chr(10), " "))
            continue
        if not isinstance(t15, dict):
            print("  t15 dict degil:", type(t15).__name__)
            continue
        t3 = t15.get("3")
        if isinstance(t3, dict):
            t3 = [t3]
        if isinstance(t3, list):
            for tc in t3:                       # 15.3 takim listesi
                tid = tc.get("1") if isinstance(tc, dict) else None
                if tid:
                    teams.setdefault(tid, tc.get("6") or tc.get("19") or "")
        t2 = t15.get("2")
        if isinstance(t2, dict):
            t2 = [t2]
        if isinstance(t2, list):
            for m in t2:                        # 15.2 maclar
                mid = m.get("1") if isinstance(m, dict) else None
                if not mid:
                    continue
                mlist.setdefault(mid, {}).update({
                    "home_id": (m.get("6") or {}).get("1") if isinstance(m.get("6"), dict) else None,
                    "away_id": (m.get("7") or {}).get("1") if isinstance(m.get("7"), dict) else None,
                    "league_id": (m.get("4") or {}).get("1") if isinstance(m.get("4"), dict) else None,
                    "start": m.get("15"),
                    "status": m.get("16"),
                })

    leagues = {}
    if isinstance(today, dict):
        _l = today.get("15", {}).get("1", []) if isinstance(today.get("15"), dict) else None
        if isinstance(_l, dict): _l = [_l]
        if isinstance(_l, list):
            for lc in _l:
                if isinstance(lc, dict) and lc.get("1"):
                    leagues[lc["1"]] = lc.get("5", "")

    print(f"takim: {len(teams)} mac: {len(mlist)} lig: {len(leagues)}")
    matches = []
    for mid, m in sorted(mlist.items(), key=lambda kv: kv[1].get("start") or 0):
        home = teams.get(m.get("home_id"), "")
        away = teams.get(m.get("away_id"), "")
        odds = {}
        try:
            odds = odds_for(mid)
        except Exception as e:
            print(mid, "odds ERR", str(e)[:100])
        matches.append({
            "match_id": mid,
            "league": leagues.get(m.get("league_id"), ""),
            "home": home,
            "away": away,
            "start": m.get("start"),
            "status": m.get("status"),
            "odds": odds,
        })
        print(f"{m.get('start')} {home[:18]:18s} vs {away[:18]:18s} "
              f"{' '.join(str(odds.get(k,{}).get('open')) for k in ['1X2','AH','OU'])}")

    out = {"generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "matches": matches}
    json.dump(out, open("upcoming.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("toplam mac:", len(matches), "| odds'lu:", sum(1 for x in matches if x["odds"]))


if __name__ == "__main__":
    main()