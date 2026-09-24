#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AiScore voleybol - GitHub Actions tam veri toplama.
Dogrudan erisim (US IP). Gunalik skor sayfalari + bet365 oranlari + NUXT meta.
Sonuc -> aiscore_full.db"""
import signal
signal.signal(signal.SIGINT, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
import re, json, time, sqlite3, datetime
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}
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

_S = requests.Session()
def get(url, timeout=15, tries=2):
    for i in range(tries):
        try:
            r = _S.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200: return r
            time.sleep(0.5 + i)
        except Exception:
            time.sleep(0.5 + i)
    return None

def scoreboard_urls(ds):
    return [f"https://www.aiscore.com/volleyball/score/{ds}",
            f"https://www.aiscore.com/volleyball/score?date={ds}",
            f"https://m.aiscore.com/volleyball/score/{ds}",
            f"https://m.aiscore.com/volleyball/score?date={ds}"]

def discover_by_scores():
    """Gunalik skor sayfalarindan mac id'leri. ~560 gun geriye."""
    found = {}
    today = datetime.date.today()
    for d in range(560, -1, -1):
        dt = today - datetime.timedelta(days=d)
        ds = dt.strftime("%Y-%m-%d")
        got = False
        for u in scoreboard_urls(ds):
            r = get(u, timeout=12)
            if not r: continue
            hits = set(re.findall(r'/volleyball/match-[^"<>?]+/([a-z0-9]{15})', r.text))
            for h in hits:
                if h not in found: found[h] = ds
            if hits: got = True
        if d % 30 == 0: log("skor gunu", d, "toplam mac", len(found))
        if not got: continue
        time.sleep(0.15)
    return found

def parse_nuxt(html):
    """NUXT payload'dan lig/ev/dep/tarih/final skor."""
    out = {}
    # __NUXT__ degerini bul
    m = re.search(r'window\.__NUXT__=(.*?)</script>', html, re.S)
    if not m:
        m = re.search(r'window\.__NUXT__=(.*?);?\s*</script>', html, re.S)
    if not m: return out
    js = m.group(1).strip()
    try:
        # (function(){...}()) seklinde ise icerideki JSON'i raw_decode ile bul
        if js.startswith("("):
            a = js.find("{")
            b = js.rfind("}")
            data = json.loads(js[a:b+1])
        else:
            data = json.loads(js)
    except Exception:
        # ilk { son } koplaj
        try:
            a = js.find("{")
            b = js.rfind("}")
            data = json.loads(js[a:b+1])
        except Exception:
            return out
    try:
        md = data["state"]["basketball"]["basketballDetailMatchData"]["match"]
        out["league"] = ((md.get("competition") or {}).get("name", ""))
        out["home"] = ((md.get("homeTeam") or {}).get("name", ""))
        out["away"] = ((md.get("awayTeam") or {}).get("name", ""))
        mt = md.get("matchTime")
        if mt: out["date"] = str(mt)
        vb = md.get("vbScores")
        if vb and vb.get("pt") and isinstance(vb["pt"], list):
            out["pt"] = [int(x) for x in vb["pt"]]
    except Exception:
        pass
    return out

def meta_worker(mid):
    out = {}
    for u in [f"https://m.aiscore.com/volleyball/match-{mid}",
              f"https://www.aiscore.com/volleyball/match-{mid}/",
              f"https://www.aiscore.com/volleyball/match-info/{mid}"]:
        r = get(u, timeout=12)
        if not r: continue
        if len(r.text) < 4000: continue
        m = parse_nuxt(r.text)
        if m.get("league") or m.get("home") or m.get("pt"):
            out = m; break
    return mid, out

def odds_worker(mid):
    try:
        r = _S.get(f"{API}/v1/m/api/match/odds/list?match_id={mid}&code=&platform=1",
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

    # seeds.txt (arsiv tabanli onceden bilinen id'ler)
    seeds = set()
    try:
        for line in open("seeds.txt", encoding="utf-8"):
            mid = line.split("\t")[0].strip()
            if len(mid) == 15 and mid not in have: seeds.add(mid)
    except FileNotFoundError:
        pass
    log("seed:", len(seeds))

    # DISCOVERY: gunluk skor sayfalari
    try:
        disc = discover_by_scores()
        log("skor sayfasi discovery:", len(disc))
        for m in disc: seeds.add(m)
    except Exception as e:
        log("discovery hata:", str(e)[:80])

    seeds -= have
    # telegram etc gibi spam id'ler ayikla (sadece 15 alfanumerik)
    seeds = {s for s in seeds if re.fullmatch(r"[a-z0-9]{15}", s)}
    log("toplam hedef:", len(seeds))
    if not seeds:
        log("yeni mac yok, bitis")
        con.close(); return

    # ODDS paralel
    odds_map = {}
    with ThreadPoolExecutor(max_workers=25) as ex:
        futs = {ex.submit(odds_worker, s): s for s in seeds}
        done = 0
        for fut in as_completed(futs):
            mid, b = fut.result()
            if b: odds_map[mid] = b
            done += 1
            if done % 300 == 0: log("odds", done, "oranli", len(odds_map))
    log("odds bitti:", len(odds_map), "/", len(seeds))
    with open("odds_dump.json", "w", encoding="utf-8") as f:
        json.dump(odds_map, f, ensure_ascii=False)

    # METADATA sadece oranlilar
    metas = {}
    if odds_map:
        with ThreadPoolExecutor(max_workers=15) as ex:
            futs = {ex.submit(meta_worker, m): m for m in odds_map}
            done = 0
            for fut in as_completed(futs):
                mid, meta = fut.result()
                if meta: metas[mid] = meta
                done += 1
                if done % 100 == 0: log("meta", done, "bulunan", len(metas))
    log("meta bitti:", len(metas))

    n = 0
    for mid, b in odds_map.items():
        meta = metas.get(mid, {})
        pt = meta.get("pt") or [None, None]
        c = re.sub(r"\s+", " ", mid)
        con.execute("INSERT OR REPLACE INTO matches VALUES(?,?,?,?,?,?,?,?)",
                    (mid, meta.get("date", ""), meta.get("league", ""),
                     meta.get("home", ""), meta.get("away", ""),
                     pt[0] if len(pt) > 0 else None,
                     pt[1] if len(pt) > 1 else None,
                     json.dumps(b, ensure_ascii=False)))
        n += 1
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    log(f"DB: {n} yeni, toplam {total}")
    con.close()

if __name__ == "__main__":
    main()