#!/usr/bin/env python3
"""Lig tespiti: DB'de league'i bos/None olan maclar icin lig adini doldurur.

Kaynaklar (oncesinde kanitlanmis):
1. /v1/web/api/matches?lang=tr&sport_id=10&date=YYYY-MM-DD  (upcoming.py lazim yapisi)
   -> 15.1 lig listesi {id: ad} , 15.2 maclar {1:mid, 4:{1:league_id}}
2. /v1/web/api/match/data?lang=tr&match_id=...  (score_grabber.py yapisi)
   -> 15.1.4.6 lig adi dogrudan

Sonuc aiscore_full.db + dataset.json'a uygulanir. GitHub Actions'ta kosulur."""
import re, json, time, sqlite3, ast
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
           "Referer": "https://www.aiscore.com/"}
API = "https://api.aiscore.com"
DB = "aiscore_full.db"
T0 = time.time()


def log(*a):
    print(f"[{time.time()-T0:6.1f}s] " + " ".join(str(x) for x in a), flush=True)


def b2s(v):
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s


def nested(o, _depth=0):
    """Python-repr dict string'lerini gercek nesneye cevir."""
    if isinstance(o, dict):
        return {k: nested(v, _depth) for k, v in o.items()}
    if isinstance(o, list):
        return [nested(v, _depth) for v in o]
    s = b2s(o)
    if s.startswith("{") or s.startswith("["):
        try:
            return nested(ast.literal_eval(s), _depth + 1)
        except Exception:
            return s
    return s


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


def get_league_by_date():
    """Tarih bazli toplu cekim. Doner: {mid: lig_adi}"""
    # DB'den tarihli + ligsiz maclari al
    con = sqlite3.connect(DB)
    todo = [(r[0], r[1]) for r in con.execute(
        "SELECT match_id, date FROM matches WHERE date != '' AND (league IS NULL OR league IN ('', 'None'))")]
    con.close()
    if not todo:
        return {}, todo
    by_date = {}
    for mid, d in todo:
        by_date.setdefault(d, []).append(mid)
    log("ligsiz+tarihli:", len(todo), "| benzersiz tarih:", len(by_date))

    out = {}
    for dt in sorted(by_date):
        try:
            r = requests.get(f"{API}/v1/web/api/matches?lang=tr&sport_id=10&date={dt}",
                             headers=HEADERS, timeout=20)
        except Exception as e:
            log("REQ ERR", dt, str(e)[:70])
            continue
        if r.status_code != 200 or len(r.content) < 60:
            continue
        try:
            msg = nested(blackboxprotobuf_decode(r.content))
        except Exception as e:
            log("DECODE", dt, str(e)[:70])
            continue
        t15 = msg.get("15", {})
        if not isinstance(t15, dict):
            continue
        leagues = {}
        for lc in (t15.get("1") if isinstance(t15.get("1"), list) else []):
            if isinstance(lc, dict) and lc.get("1"):
                leagues[str(lc["1"])] = b2s(lc.get("5") or lc.get("6") or "")
        macs = t15.get("2")
        if isinstance(macs, dict):
            macs = [macs]
        for m in (macs if isinstance(macs, list) else []):
            if not isinstance(m, dict) or not m.get("1"):
                continue
            mid = str(m["1"])
            if mid not in by_date.get(dt, []):
                continue
            lid = None
            if isinstance(m.get("4"), dict):
                lid = m["4"].get("1")
            lname = leagues.get(str(lid), "").strip()
            if not lname and isinstance(m.get("4"), dict):
                lname = b2s(m["4"].get("6") or m["4"].get("5") or "").strip()
            if lname:
                out[mid] = lname
        time.sleep(0.15)
    log("tarih-bazli bulunan lig:", len(out))
    return out, todo


def blackboxprotobuf_decode(content):
    import blackboxprotobuf
    return blackboxprotobuf.decode_message(content)[0]


def match_worker(mid):
    """Bireysel fallback: match/data -> mobj.4.6 lig adi."""
    try:
        for attempt in range(4):
            r = requests.get(f"{API}/v1/web/api/match/data?lang=tr&match_id={mid}",
                             headers=HEADERS, timeout=20)
            if r.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code != 200:
                return mid, None
            msg = blackboxprotobuf_decode(r.content)
            break
        else:
            return mid, None
    except Exception:
        return mid, None
    mobj = parse15(msg.get("15", {}))
    if not mobj:
        return mid, None
    ln = b2s((mobj.get("4") or {}).get("6") or (mobj.get("4") or {}).get("5") or "").strip()
    return mid, ln or None


PREFIXES = ["Women", "Men", "Boys", "Girls"]


def team_hint(meta):
    """Takim adlarindan kategori ipucu (avci yontem, lig adi degil)."""
    gm = " ".join([meta.get("home", ""), meta.get("away", "")])
    for p in PREFIXES:
        if p in gm:
            return p
    return ""


def main():
    by_date, todo = get_league_by_date()
    con = sqlite3.connect(DB)
    mid_done = set(by_date.keys())

    # gerekli set: tarihli ama bulunamayan + tarihsiz olanlar
    rest = [mid for mid, d in todo if mid not in mid_done]
    rest += [r[0] for r in con.execute(
        "SELECT match_id FROM matches WHERE date = '' AND (league IS NULL OR league IN ('', 'None'))")]
    rest = list(dict.fromkeys(rest))
    log("bireysel fallback kalan:", len(rest))

    ml = {}
    if rest:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(match_worker, m): m for m in rest}
            done = 0
            for fut in as_completed(futs):
                mid, ln = fut.result()
                if ln:
                    ml[mid] = ln
                done += 1
                if done % 100 == 0:
                    log("fallback", done, "/", len(rest), "bulunan:", len(ml))
    log("fallback bulunan:", len(ml))

    all_found = dict(by_date)
    all_found.update(ml)
    log("TOPLAM yeni lig:", len(all_found))

    # DB'ye uygula
    updated = 0
    metas = {}
    for r in con.execute("SELECT match_id, home, away FROM matches"):
        metas[r[0]] = (r[1], r[2])
    for mid, ln in all_found.items():
        con.execute("UPDATE matches SET league=? WHERE match_id=?", (ln, mid))
        updated += 1
    con.commit()

    # hic bulunamayanlar icin takim hint'i (sadece bilgi; lig adi bilinmiyor)
    missed = [mid for mid, d in todo if mid not in all_found]
    missed += [r[0] for r in con.execute(
        "SELECT match_id FROM matches WHERE date = '' AND (league IS NULL OR league IN ('', 'None'))")]
    missed = list(dict.fromkeys(m for m in missed if m not in all_found))
    hints = {}
    for mid in missed:
        try:
            h, a = metas.get(mid, ("", ""))
            hx = team_hint({"home": h, "away": a})
            if hx:
                hints[mid] = hx
        except Exception:
            pass
    log("bulunamayan:", len(missed), "| kategori ipucu olan:", len(hints))

    # dataset.json'i yeniden uret (tutarlilik)
    recs = []
    for r in con.execute("SELECT match_id,date,league,home,away,pt_home,pt_away,bet365_json,sets_json FROM matches"):
        odds = {}
        try:
            odds = json.loads(r[7])
        except Exception:
            pass
        sets = []
        if r[8]:
            try:
                sets = json.loads(r[8])
            except Exception:
                pass
        recs.append({"id": r[0], "date": r[1], "league": r[2], "home": r[3], "away": r[4],
                     "pt": [r[5], r[6]] if r[5] is not None else None,
                     "sets": sets, "odds": odds})
    json.dump(recs, open("dataset.json", "w", encoding="utf-8"), ensure_ascii=False)
    leagues_left = sum(1 for r in con.execute("SELECT league FROM matches") if (r[0] or "") in ("", "None"))
    leagues_now = sum(1 for r in con.execute("SELECT league FROM matches") if r[0] and r[0] not in ("", "None"))
    log(f"dataset.json: {len(recs)} kayit | ligli={leagues_now} hala-bos={leagues_left}")
    con.close()
    print("DONE")


if __name__ == "__main__":
    main()