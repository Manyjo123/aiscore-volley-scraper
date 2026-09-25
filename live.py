#!/usr/bin/env python3
"""aiscore canlı voleybol → live.json üretici.
today/matches + match/data (set skorları) + odds/list (bet365 açılış/canlı oran).
Canlı tespiti: maç başlamış (set skoru var) ve bitmemiş (final net skor yok)."""
import json, io, sys, time, ast, datetime
import requests
import blackboxprotobuf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.aiscore.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
           "Referer": "https://www.aiscore.com/"}
BET365_ID = 2
MARKET_NAMES = {"1": "AH", "2": "1X2", "3": "OU", "5": "OU2"}
CANLI_STATUS = {"1", "2", "3", "432", "433", "434", "438"}


def b2s(v):
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s


def resolve(o):
    """blackbox string-parsed dicts'i gerçek nesneye çevir."""
    if isinstance(o, str):
        s = o.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                return resolve(ast.literal_eval(s))
            except Exception:
                return o
        return o
    if isinstance(o, list): return [resolve(x) for x in o]
    if isinstance(o, dict): return {k: resolve(v) for k, v in o.items()}
    return o


def clean(o):
    if isinstance(o, dict): return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [clean(b2s(v)) for v in o]
    return b2s(o)


def get_proto(path, timeout=20, _dbg=False):
    try:
        r = requests.get(API + path, headers=HEADERS, timeout=timeout)
    except Exception as e:
        print("REQ ERR", path[:40], str(e)[:90])
        return None
    if r.status_code != 200:
        print("HTTP", r.status_code, path[:40])
        return None
    if len(r.content) < 40:
        print("SHORT", len(r.content), path[:40])
        return None
    try:
        msg = blackboxprotobuf.decode_message(r.content)[0]
    except Exception as e:
        print("DECODE ERR", path[:40], str(e)[:90])
        return None
    try:
        return clean(resolve(msg))
    except Exception as e:
        print("RESOLVE ERR", path[:40], str(e)[:90])
        return None


def extract_bet365(f15):
    out = {}
    if not isinstance(f15, dict):
        return out
    for mkey, mname in MARKET_NAMES.items():
        entries = f15.get(mkey, [])
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            continue
        for e in entries:
            try:
                cid = int(e.get("3", {}).get("1", -1))
            except Exception:
                continue
            if cid != BET365_ID:
                continue
            o = e.get("1", {}).get("1", []); c = e.get("2", {}).get("1", [])
            cur = e.get("4", {}).get("1", [])
            out[mname] = {"open": [b2s(x) for x in o] if isinstance(o, list) else [],
                          "close": [b2s(x) for x in c] if isinstance(c, list) else [],
                          "current": [b2s(x) for x in cur] if isinstance(cur, list) else [],
                          "company": "bet365"}
    return out


def main():
    today = get_proto("/v1/web/api/today/matches?sid=10&tz=08:00&lang=tr")
    ml = []
    leagues = {}
    teams = {}
    if isinstance(today, dict) and isinstance(today.get("15"), dict):
        t15 = today["15"]
        for lc in (t15.get("1") if isinstance(t15.get("1"), list) else []):
            if isinstance(lc, dict) and lc.get("1"):
                leagues[lc["1"]] = lc.get("5", "")
        for tc in (t15.get("3") if isinstance(t15.get("3"), list) else []):
            if isinstance(tc, dict) and tc.get("1"):
                teams[tc["1"]] = tc.get("6") or tc.get("19") or ""
        for m in (t15.get("2") if isinstance(t15.get("2"), list) else []):
            if not isinstance(m, dict) or not m.get("1"):
                continue
            mid = m.get("1")
            home_id = None; away_id = None; league_id = None
            if isinstance(m.get("6"), dict): home_id = m["6"].get("1")
            if isinstance(m.get("7"), dict): away_id = m["7"].get("1")
            if isinstance(m.get("4"), dict): league_id = m["4"].get("1")
            ml.append({
                "match_id": mid, "league_id": league_id,
                "home_id": home_id, "away_id": away_id,
                "start": m.get("15"), "status": m.get("16"),
            })
    print("today maç:", len(ml), "lig:", len(leagues))

    matches = []
    for m in ml:
        mid = m["match_id"]
        # 20sn'lik rahat — Actions hızı
        data = get_proto("/v1/web/api/match/data?lang=tr&match_id=%s" % mid, timeout=15)
        f = {}
        if isinstance(data, dict):
            o15 = data.get("15")
            if isinstance(o15, dict):
                f = o15.get("1", {}).get("108", {})
        # set skorları (bytes listeleri)
        sets = []
        for k in ("1", "2", "3", "4", "5", "6"):
            v = f.get(k)
            if isinstance(v, list) and len(v) >= 2:
                sets.append([int(x) for x in v[:2]])
        sh = sa = 0
        for s in sets:
            if s[0] > s[1]: sh += 1
            elif s[1] > s[0]: sa += 1
        # net skor alanı (set6 = final setler, ör [3,0])
        final = None
        f6 = f.get("6")
        if isinstance(f6, list) and len(f6) >= 2:
            final = [int(f6[0]), int(f6[1])]
        is_live = bool(sets) and final is None
        if m.get("status") in CANLI_STATUS and final is None and sets:
            is_live = True
        if not is_live:
            continue
        odds = extract_bet365(data.get("15", {}).get("1", {}) if isinstance(data.get("15"), dict) else {})
        if not odds:
            od = get_proto("/v1/m/api/match/odds/list?match_id=%s&code=&platform=1" % mid, timeout=15)
            if isinstance(od, dict):
                odds = extract_bet365(od.get("15", {}).get("1", {}) if isinstance(od.get("15"), dict) else {})
        matches.append({
            "match_id": mid,
            "league": leagues.get(m.get("league_id"), ""),
            "home": teams.get(m.get("home_id"), ""),
            "away": teams.get(m.get("away_id"), ""),
            "start": m.get("start"),
            "status": m.get("status"),
            "set_home": sh, "set_away": sa,
            "pt_home": sum(s[0] for s in sets) if sets else 0,
            "pt_away": sum(s[1] for s in sets) if sets else 0,
            "odds": odds,
        })
        print("LIVE", sh, "-", sa, teams.get(m.get("home_id"), "")[:18], "vs",
              teams.get(m.get("away_id"), "")[:18],
              "st=", m.get("status"), "1X2 cur:", odds.get("1X2", {}).get("current"))
        time.sleep(0.3)

    out = {"generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "matches": matches}
    json.dump(out, open("live.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("live.json yazıldı:", len(matches), "canlı maç")


if __name__ == "__main__":
    main()