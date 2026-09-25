#!/usr/bin/env python3
"""match/data endpoint'inden PHP.php: tek istekle set skorlari + pt + lig/ev/dep/tarih.
DB'de skorsuz (pt_home NULL) tum maclari doldurur, veri seti yedigini yeniden uretir."""
import re, json, time, sqlite3, ast
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
API = "https://api.aiscore.com"
T0 = time.time()

def log(*a):
    print(f"[{time.time()-T0:6.1f}s] " + " ".join(str(x) for x in a), flush=True)

def parse15(o):
    """15 field'i dict veya str(dict literal) olabilir."""
    if isinstance(o, str):
        s = o.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                o = ast.literal_eval(s)
            except Exception:
                return {}
    return o if isinstance(o, dict) else {}

def score_worker(mid):
    try:
        r = requests.get(f"{API}/v1/web/api/match/data?lang=tr&match_id={mid}",
                         headers=HEADERS, timeout=25)
        if r.status_code != 200:
            return mid, {"err": f"HTTP {r.status_code}"}
        import blackboxprotobuf
        msg, _ = blackboxprotobuf.decode_message(r.content)
        f15 = parse15(msg.get("15", {}))
        mobj = f15.get("1", {})
        if not isinstance(mobj, dict):
            return mid, {"err": "no mobj", "f15keys": list(f15.keys())[:8]}
        sets = []
        s6 = None
        vb = mobj.get("108", {})
        if isinstance(vb, dict):
            for k in ("1", "2", "3", "4", "5"):
                v = vb.get(k)
                if isinstance(v, bytes) and len(v) >= 2:
                    sets.append([int(v[0]), int(v[1])])
            v6 = vb.get("6")
            if isinstance(v6, bytes) and len(v6) >= 2:
                s6 = [int(v6[0]), int(v6[1])]
        pt = None
        if sets:
            pt = [sum(s[0] for s in sets), sum(s[1] for s in sets)]
        def nm(d): return (d or {}).get("6")
        probe = None
        if not sets:
            probe = {"has108": "108" in mobj, "has15": "15" in f15,
                     "keys108": list(mobj.get("108", {}) or {}).keys() if isinstance(mobj.get("108"), dict) else "no108",
                     "topkeys": list(f15.keys())[:10]}
        return mid, {
            "date": int_to_date(mobj.get("15")),
            "league": b2s(nm(mobj.get("4"))),
            "home": b2s(nm(mobj.get("6"))),
            "away": b2s(nm(mobj.get("7"))),
            "sets": sets, "setw": s6, "pt": pt, "probe": probe,
        }
    except Exception as e:
        return mid, {"err": str(e)[:80]}

def b2s(v):
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s

def int_to_date(ts):
    if not isinstance(ts, (int, float)): return None
    import datetime
    return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")

def main():
    db = "aiscore_full.db"
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(matches)")]
    if "sets_json" not in cols:
        con.execute("ALTER TABLE matches ADD COLUMN sets_json TEXT")
    todo = [r[0] for r in con.execute("SELECT match_id FROM matches WHERE pt_home IS NULL")]
    log("skorsuz:", len(todo))
    got, errs, nop = 0, 0, 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(score_worker, m): m for m in todo}
        for fut in as_completed(futs):
            mid, o = fut.result()
            if "err" in o:
                errs += 1
                if errs <= 5: log("hata", mid, o["err"])
                continue
            if o["probe"]:
                nop += 1
                if nop <= 8: log("probe", mid, json.dumps(o["probe"])[:170])
                continue
            got += 1
            cur = con.execute("SELECT date, home FROM matches WHERE match_id=?", (mid,)).fetchone()
            fillN = lambda old, new: old if old else (new or "")
            con.execute("UPDATE matches SET date=?, league=?, home=?, away=?, pt_home=?, pt_away=?, sets_json=? WHERE match_id=?",
                        (fillN(cur[0], o["date"]), o["league"], fillN(cur[1], o["home"]), o["away"],
                         o["pt"][0], o["pt"][1], json.dumps(o["sets"]) if o["sets"] else None, mid))
    con.commit()
    log(f"cekildi={got} hata={errs} skorsuz-kalan={nop}")
    # bos meta'lari da doldur (tarih/lig/ev/dep)
    recs = []
    for r in con.execute("SELECT match_id,date,league,home,away,pt_home,pt_away,bet365_json,sets_json FROM matches"):
        odds = {}
        try: odds = json.loads(r[7])
        except Exception: pass
        sets = []
        if r[8]:
            try: sets = json.loads(r[8])
            except Exception: pass
        recs.append({"id": r[0], "date": r[1], "league": r[2], "home": r[3], "away": r[4],
                     "pt": [r[5], r[6]] if r[5] is not None else None,
                     "sets": sets, "odds": odds})
    json.dump(recs, open("dataset.json", "w", encoding="utf-8"), ensure_ascii=False)
    scored = sum(1 for r in con.execute("SELECT pt_home FROM matches") if r[0] is not None)
    sets_cnt = sum(1 for r in con.execute("SELECT sets_json FROM matches") if r[0])
    log(f"dataset.json: {len(recs)} kayit | skorlu={scored} setli={sets_cnt}")
    con.close()

if __name__ == "__main__":
    main()