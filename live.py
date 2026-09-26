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
    if v is None:
        return ""
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s


def clean(o):
    if isinstance(o, dict): return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [clean(b2s(v)) for v in o]
    return b2s(o)


def nested(o):
    """Python-repr dict string'lerini gerçek nesneye çevir (probe'da kanıtlanan yol)."""
    if isinstance(o, dict): return {k: nested(b2s(v)) for k, v in o.items()}
    if isinstance(o, list): return [nested(b2s(v)) for v in o]
    s = b2s(o)
    if s.startswith("{") or s.startswith("["):
        try:
            return nested(ast.literal_eval(s))
        except Exception:
            return s
    return s


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
        return nested(msg)
    except Exception as e:
        print("RESOLVE ERR", path[:40], str(e)[:90])
        return None


def parse15(o):
    """15 field'i dict veya str(dict literal) olabilir."""
    if isinstance(o, str):
        s = o.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                o = ast.literal_eval(s)
            except Exception:
                return {}
    if isinstance(o, dict):
        m = o.get("1", {})
        if isinstance(m, dict):
            return m
    return {}


def get_match_score(mid):
    """score_grabber ile kanıtlanmış: match/data → mobj → 108 bytes set skorları.
    canlı = set var ama final(setw=108.6) yok."""
    try:
        for attempt in range(3):
            r = requests.get(f"{API}/v1/web/api/match/data?lang=tr&match_id={mid}",
                             headers=HEADERS, timeout=20)
            if r.status_code == 429:
                import time as _t
                _t.sleep(1.0 * (attempt + 1))
                continue
            if r.status_code != 200:
                return None
            msg, _ = blackboxprotobuf.decode_message(r.content)
            break
        else:
            return None
    except Exception as e:
        return None
    mobj = parse15(msg.get("15", {}))
    if not mobj:
        return None
    vb = mobj.get("108", {})
    if not isinstance(vb, dict):
        return None
    sets = []
    for k in ("1", "2", "3", "4", "5"):
        v = vb.get(k)
        if isinstance(v, bytes) and len(v) >= 2:
            sets.append([int(v[0]), int(v[1])])
    s6 = None
    v6 = vb.get("6")
    if isinstance(v6, bytes) and len(v6) >= 2:
        s6 = [int(v6[0]), int(v6[1])]
    return {"sets": sets, "final": s6,
            "league": b2s((mobj.get("4") or {}).get("6")),
            "home": b2s((mobj.get("6") or {}).get("6")),
            "away": b2s((mobj.get("7") or {}).get("6"))}


def row_val(r, idx):
    """selection row → dizi[idx]. r={"1": [ev, line, dep, 0]}."""
    try:
        d = r.get("1")
        if isinstance(d, dict):
            d = d.get("1")
        if isinstance(d, list) and len(d) > idx:
            o = str(d[idx])
            if o.replace(".", "").replace(",", "").isdigit():
                return o
    except Exception:
        pass
    return None


def extract_bet365(msg):
    """15.{market}: {1: açılış row, 2: anlık row, 3:{'1':company}, 4: yedek}.
    row=[ev_oran, line, dep_oran, 0]. market2=1X2."""
    out = {}
    try:
        f15 = msg.get("15")
    except Exception:
        return out
    if not isinstance(f15, dict):
        return out
    for mkey, mname in MARKET_NAMES.items():
        m = f15.get(mkey)
        if not isinstance(m, dict):
            continue
        try:
            company = int((m.get("3") or {}).get("1", -1))
        except Exception:
            company = -1
        if company != BET365_ID:
            continue
        r_open = m.get("1")
        r_cur = m.get("2") or m.get("4")
        if not (isinstance(r_open, dict) and isinstance(r_cur, dict)):
            continue
        oev, ode = row_val(r_open, 0), row_val(r_open, 2)
        cev, cde = row_val(r_cur, 0), row_val(r_cur, 2)
        if not (oev and ode):
            continue
        if not cev:
            cev, cde = oev, ode
        out[mname] = {"open": [oev, "0", ode, "0"],
                      "close": [oev, "0", ode, "0"],
                      "current": [cev, "0", cde, "0"],
                      "company": "bet365"}
    return out


def odds_for(mid):
    """upcoming.py ile kanıtlanmış: /v1/m/api/match/odds/list → extract_bet365."""
    try:
        r = requests.get(f"{API}/v1/m/api/match/odds/list?match_id={mid}&code=&platform=1",
                         headers=HEADERS, timeout=15)
        if len(r.content) < 100:
            return {}
        msg = blackboxprotobuf.decode_message(r.content)[0]
        return extract_bet365(nested(msg))
    except Exception:
        return {}


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
        sc = get_match_score(mid)
        sets = sc["sets"] if sc else []
        final = sc["final"] if sc else None
        sh = sa = 0
        for s in sets:
            if s[0] > s[1]: sh += 1
            elif s[1] > s[0]: sa += 1
        is_live = (bool(sets) and final is None
                   and sh < 3 and sa < 3
                   and str(m.get("status")) != "100")
        hname = (sc or {}).get("home") or teams.get(m.get("home_id"), "")
        aname = (sc or {}).get("away") or teams.get(m.get("away_id"), "")
        lleague = (sc or {}).get("league") or leagues.get(m.get("league_id"), "")
        if not is_live:
            continue
        odds = odds_for(mid)
        matches.append({
            "match_id": mid,
            "league": lleague,
            "home": hname,
            "away": aname,
            "start": m.get("start"),
            "status": m.get("status"),
            "set_home": sh, "set_away": sa,
            "sets": sets,
            "pt_home": sum(s[0] for s in sets) if sets else 0,
            "pt_away": sum(s[1] for s in sets) if sets else 0,
            "odds": odds,
        })
        print("LIVE", sh, "-", sa, hname[:18], "vs", aname[:18],
              "st=", m.get("status"), "setler:", sets,
              "1X2 cur:", odds.get("1X2", {}).get("current"))
        time.sleep(0.3)

    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "matches": matches}
    json.dump(out, open("live.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("live.json yazıldı:", len(matches), "canlı maç")


if __name__ == "__main__":
    main()