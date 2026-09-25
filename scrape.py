#!/usr/bin/env python3
"""AiScore voleybol - GitHub Actions: API uzerinden bet365 oranlari.
Dogrudan erisim: api.aiscore.com (list endpoint yok, HTML 403 ama odds calisiyor).
seeds.txt'teki tum mac id'leri icin odds. Skor/lig bilgisi yereldeki arsiv HTML'lerinde."""
import signal
signal.signal(signal.SIGINT, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
import re, json, time, sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
API = "https://api.aiscore.com"
BET365_ID = 2
MARKET_NAMES = {"1": "AH", "2": "1X2", "3": "OU", "5": "OU2"}
T0 = time.time()

def log(*a):
    print(f"[{time.time()-T0:6.1f}s] " + " ".join(str(x) for x in a), flush=True)

def b2s(v):
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s

def decode_odds(content):
    import blackboxprotobuf
    return blackboxprotobuf.decode_message(content)[0]

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

def odds_worker(mid):
    try:
        r = requests.get(f"{API}/v1/m/api/match/odds/list?match_id={mid}&code=&platform=1",
                         headers=HEADERS, timeout=20)
        if len(r.content) < 100: return mid, {}
        return mid, extract_bet365(decode_odds(r.content))
    except Exception:
        return mid, {}

def main():
    con = sqlite3.connect("aiscore_full.db")
    con.execute("""CREATE TABLE IF NOT EXISTS matches(match_id TEXT PRIMARY KEY,
        date TEXT, league TEXT, home TEXT, away TEXT, pt_home INT, pt_away INT,
        bet365_json TEXT)""")
    have = {r[0] for r in con.execute("SELECT match_id FROM matches")}
    seeds = {}
    for line in open("seeds.txt", encoding="utf-8"):
        parts = line.strip().split("\t")
        mid = parts[0]
        if re.fullmatch(r"[a-z0-9]{15}", mid) and mid not in have:
            seeds[mid] = parts[1] if len(parts) > 1 else ""
    log("hedef (yeni):", len(seeds))

    odds_map = {}
    with ThreadPoolExecutor(max_workers=25) as ex:
        futs = {ex.submit(odds_worker, m): m for m in seeds}
        done = 0
        for fut in as_completed(futs):
            mid, b = fut.result()
            if b: odds_map[mid] = b
            done += 1
            if done % 300 == 0: log("odds", done, "oranli", len(odds_map))
    log("odds bitti:", len(odds_map), "oranli /", len(seeds), "hedef")

    n = 0
    markets = {k: 0 for k in MARKET_NAMES.values()}
    for mid, b in odds_map.items():
        for mk in b: markets[mk] += 1
        con.execute("INSERT OR REPLACE INTO matches(match_id, bet365_json) VALUES(?,?)",
                    (mid, json.dumps(b, ensure_ascii=False)))
        n += 1
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    log("DB toplam:", total, "| pazar dagilimi:", dict(markets))
    with open("odds_dump.json", "w", encoding="utf-8") as f:
        json.dump(odds_map, f, ensure_ascii=False)
    con.close()

if __name__ == "__main__":
    main()