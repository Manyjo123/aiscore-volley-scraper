#!/usr/bin/env python3
"""AiScore voleybol - GitHub Actions TAM PIPELINE.
1) api.aiscore.com'dan bet365 odds (tum seed'ler)
2) web.archive.org'dan mac sayfa HTML'leri (rate-limit'e saygi)
3) NUXT regex parse -> lig/ev/dep/tarih/final skor
Sonuc -> aiscore_full.db"""
import signal
signal.signal(signal.SIGINT, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
import re, json, time, sqlite3, datetime
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
API = "https://api.aiscore.com"
ARCH = "https://web.archive.org"
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

# ---- seeds + cdx listeleri ----
def load_seeds():
    seeds = set()
    for line in open("seeds.txt", encoding="utf-8"):
        mid = line.split("\t")[0].strip()
        if re.fullmatch(r"[a-z0-9]{15}", mid): seeds.add(mid)
    return seeds

def load_cdx():
    """cdx listelerinden (repo'ya kopyalanmis) mac id -> en guncel snapshot.
    www (desktop) snapshot'lari mobil (m.) olanlara tercih edilir."""
    best = {}
    for fn in ["cdx_all.json", "cdx_mobile.json"]:
        try:
            rows = json.load(open(fn, encoding="utf-8"))
        except FileNotFoundError:
            continue
        for r in rows[1:]:
            u = r[0]
            if "match-" not in u or u.rstrip("/").endswith("/odds"): continue
            mid = u.rstrip("/").split("/")[-1]
            if not re.fullmatch(r"[a-z0-9]{15}", mid): continue
            cur = best.get(mid)
            score = (1 if "www." in u else 0, r[1])  # once www, sonra en guncel
            if cur is None or score > cur[0]:
                best[mid] = (score, r[1], u)
    return {m: (v[1], v[2]) for m, v in best.items()}

def odds_worker(mid):
    try:
        r = requests.get(f"{API}/v1/m/api/match/odds/list?match_id={mid}&code=&platform=1",
                         headers=HEADERS, timeout=20)
        if len(r.content) < 100: return mid, {}
        return mid, extract_bet365(decode_odds(r.content))
    except Exception:
        return mid, {}

def parse_meta(html):
    """Regex ile NUXT icinden meta cikar (JSON islemi gerektirmez)."""
    out = {}
    m = re.search(r'"competition":\{"name":"([^"]+)"', html)
    if m: out["league"] = m.group(1)
    m = re.search(r'"homeTeam":\{"name":"([^"]+)"', html)
    if m: out["home"] = m.group(1)
    m = re.search(r'"awayTeam":\{"name":"([^"]+)"', html)
    if m: out["away"] = m.group(1)
    m = re.search(r'"matchTime":(\d{9,11})', html)
    if m:
        try:
            out["date"] = datetime.datetime.fromtimestamp(int(m.group(1))).strftime("%Y-%m-%d")
        except Exception: pass
    m = re.search(r'"vbScores":\{[^}]*"pt":\[(\d+),(\d+)\]', html)
    if m:
        out["pt"] = [int(m.group(1)), int(m.group(2))]
    else:
        # mobil sayfa: set skorlari rendered HTML'de 'scoreText' divleri
        pairs = re.findall(r'<div class="col flex-1"><div class="scoreText(?: colorMax)?">\s*(\d+|-)\s*</div> <div class="scoreText(?: colorMax)?">\s*(\d+|-)\s*</div>', html)
        nums = [(int(a), int(b)) for a, b in pairs if a != '-' and b != '-']
        if len(nums) >= 2:
            out["pt"] = [sum(a for a, b in nums), sum(b for a, b in nums)]
    return out

def arc_worker(mid, ts, u):
    url = f"{ARCH}/web/{ts}id_/{u}"
    for attempt in range(6):
        try:
            r = requests.get(url, headers=HEADERS, timeout=50)
            if r.status_code == 200 and len(r.text) > 8000:
                meta = parse_meta(r.text)
                meta["_ok"] = True
                return mid, meta
            if r.status_code == 429:
                time.sleep(8 + attempt * 5)   # rate-limit backoff
                continue
            if r.status_code in (502, 503, 504):
                time.sleep(4 + attempt * 3)
                continue
            return mid, {"_ok": False}
        except Exception:
            time.sleep(3 + attempt * 3)
    return mid, {"_ok": False}

def main():
    db = "aiscore_full.db"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS matches(match_id TEXT PRIMARY KEY,
        date TEXT, league TEXT, home TEXT, away TEXT, pt_home INT, pt_away INT,
        bet365_json TEXT)""")
    cols = [r[1] for r in con.execute("PRAGMA table_info(matches)")]
    if "sets_json" not in cols:
        con.execute("ALTER TABLE matches ADD COLUMN sets_json TEXT")
    existing = {}
    for r in con.execute("SELECT match_id, date, league, pt_home, bet365_json FROM matches"):
        existing[r[0]] = (r[1], r[2], r[4])
    log("DB'de mevcut:", len(existing))

    seeds = load_seeds()
    cdx = load_cdx()
    targets = seeds | set(cdx.keys())
    # zaten odds'lu ve meta'li olanlari atla
    to_fetch = [m for m in targets if m not in existing]
    log("yeni hedef:", len(to_fetch), "| mevcut oranli:", sum(1 for v in existing.values() if v[2]))

    # 1) ODDS (sadece yeni)
    odds_map = {}
    if to_fetch:
        with ThreadPoolExecutor(max_workers=25) as ex:
            futs = {ex.submit(odds_worker, m): m for m in to_fetch}
            done = 0
            for fut in as_completed(futs):
                mid, b = fut.result()
                if b: odds_map[mid] = b
                done += 1
                if done % 400 == 0: log("odds", done, "oranli", len(odds_map))
        log("yeni odds:", len(odds_map), "/", len(to_fetch))
    else:
        log("yeni odds yok (hepsi DB'de)")

    # 2) ARSIV (sadece skorsuz/ozetsiz odds'lular)
    need_meta = [m for m in odds_map if m not in existing] + \
                [m for m in existing if existing[m][0] == "" and m in cdx]
    need_meta = list(dict.fromkeys(need_meta))
    metas = {}
    t0 = time.time()
    ARCH_BUDGET = 680   # saniye siniri (~11dk)
    if need_meta:
        import threading, queue
        q = queue.Queue()
        for m in need_meta: q.put(m)
        lock = threading.Lock()
        def wkr():
            while True:
                try: mid = q.get(timeout=2)
                except queue.Empty: return
                ts, u = cdx[mid]
                r = arc_worker(mid, ts, u)
                if r[1].get("_ok"):
                    with lock: metas[r[0]] = r[1]
        ths = [threading.Thread(target=wkr, daemon=True) for _ in range(4)]
        for th in ths: th.start()
        while time.time() - t0 < ARCH_BUDGET:
            time.sleep(5)
            with lock:
                done = q.empty()
            if done: break
        log("arsiv meta (budget):", len(metas), f"{time.time()-t0:.0f}s")
    else:
        log("arsiv gereken yok")

    # 3) DB (mevcut + yeni birlestir, arsiv meta'larini uygula)
    mk = {k: 0 for k in MARKET_NAMES.values()}
    n = 0
    for mid, b in odds_map.items():
        for k in b: mk[k] += 1
        meta = metas.get(mid, {})
        pt = meta.get("pt") or [None, None]
        con.execute("INSERT OR REPLACE INTO matches VALUES(?,?,?,?,?,?,?,?,?)",
                    (mid, meta.get("date", ""), meta.get("league", ""),
                     meta.get("home", ""), meta.get("away", ""),
                     pt[0] if len(pt) > 0 else None,
                     pt[1] if len(pt) > 1 else None,
                     json.dumps(b, ensure_ascii=False),
                     None))
        n += 1
    # existing satirlar icin arsiv meta varsa guncelle
    if metas:
        for mid, meta in metas.items():
            cur = con.execute("SELECT date, league FROM matches WHERE match_id=?", (mid,)).fetchone()
            if not cur: continue
            if cur[0] or not meta.get("date"): continue  # zaten meta'li
            pt = meta.get("pt") or [None, None]
            con.execute("UPDATE matches SET date=?, league=?, home=?, away=?, pt_home=?, pt_away=? WHERE match_id=?",
                        (meta.get("date", ""), meta.get("league", ""),
                         meta.get("home", ""), meta.get("away", ""),
                         pt[0] if len(pt) > 0 else None,
                         pt[1] if len(pt) > 1 else None, mid))
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    scored = sum(1 for r in con.execute("SELECT pt_home FROM matches") if r[0] is not None)
    dated = sum(1 for r in con.execute("SELECT date FROM matches") if r[0])
    log(f"DB: total={total} skorlu={scored} tarihli={dated} markets={mk}")
    with open("aiscore_full.json", "w", encoding="utf-8") as f:
        json.dump({m: odds_map[m] for m in odds_map}, f, ensure_ascii=False)
    # app icin tam DB dump (gelistirme verisi)
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
                     "pt": [r[5], r[6]] if r[5] is not None else None, "sets": sets, "odds": odds})
    with open("dataset.json", "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False)
    log("dataset.json:", len(recs), "kayit")
    con.close()

if __name__ == "__main__":
    main()