#!/usr/bin/env python3
"""Bugun + gelecek voleybol maclarinin bet365 acilis oranlarini
/v1/web/api/today/matches (sid=10) ve /matches/future uzerinden ceker,
upcoming.json uretir. App'in gunluk veri kaynagi."""
import json, time, datetime
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


def clean(o):
    if isinstance(o, dict): return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [clean(b2s(v)) for v in o]
    return b2s(o)


def get_json(name, path):
    url = API + path
    r = requests.get(url, headers=HEADERS, timeout=20)
    try:
        msg, _ = blackboxprotobuf.decode_message(r.content)
        return clean(msg)
    except Exception as e:
        print(name, "DECODE ERR", str(e)[:150])
        return None


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
        if not src:
            continue
        t15 = src.get("15", {})
        for tc in t15.get("3", []):                       # 15.3 takim listesi
            tid = tc.get("1")
            if tid:
                teams.setdefault(tid, tc.get("6") or tc.get("19") or "")
        for m in t15.get("2", []):                        # 15.2 maclar
            mid = m.get("1")
            if not mid:
                continue
            mlist.setdefault(mid, {}).update({
                "home_id": (m.get("6") or {}).get("1"),
                "away_id": (m.get("7") or {}).get("1"),
                "league_id": (m.get("4") or {}).get("1"),
                "start": m.get("15"),
                "status": m.get("16"),
            })

    leagues = {}
    if today:
        for lc in today.get("15", {}).get("1", []):
            if lc.get("1"):
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