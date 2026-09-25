import json, sys, time, gzip, io
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip, deflate, br"})

DOMAINS = [
    "https://1xbet.com",
    "https://1xbet.kz",
    "https://1xstake.com",
    "https://reg.1xbet.com",
]

def fetch(url, params):
    try:
        r = S.get(url, params=params, timeout=20)
        ct = r.headers.get("Content-Type", "")
        if "gzip" in ct or r.content[:2] == b"\x1f\x8b":
            try:
                return json.loads(gzip.decompress(r.content))
            except Exception:
                pass
        try:
            return r.json()
        except Exception:
            return {"raw_preview": r.content[:200].decode("utf-8", "replace")}
    except Exception as e:
        return {"error": str(e)}

def main():
    out = {}
    # 1) sport listesi (voleybol id bul)
    for d in DOMAINS:
        data = fetch(d + "/LineFeed/GetSportsShortZip",
                     {"sports": 0, "lng": "tr", "tf": 1000000, "country": 1})
        out["sports"] = data
        if isinstance(data, dict) and ("Value" in data):
            break
        print(f"sport deneme: {d} -> {json.dumps(data)[:200]}", flush=True)
        time.sleep(1)

    val = out["sports"]
    volley_id = None
    if isinstance(val, dict) and isinstance(val.get("Value"), list):
        for s in val["Value"]:
            name = (s.get("N") or "").lower()
            if "vole" in name:
                volley_id = s.get("I")
                out["volley_sport"] = s
                print(f"VOLEYBOL sport id={volley_id} name={s.get('N')}", flush=True)
                break
        if volley_id is None:
            print("voleybol bulunamadi, tum sporlar ozet:", flush=True)
            for s in val["Value"][:40]:
                print("   ", s.get("I"), s.get("N"), flush=True)

    # 2) voleybol hat / onceki maclar
    sid = volley_id or 6
    params = {
        "sport": sid, "lng": "tr", "tf": 1000000, "tz": 5, "country": 1,
        "count": 50, "group": "champ",
    }
    data = fetch(DOMAINS[0] + "/LineFeed/GetChampsZip", params)
    out["champs"] = data
    print("CHAMPS:", json.dumps(data)[:400], flush=True)

    # 3) get-empty maç listesi (yaklaşan)
    params = {
        "sports": sid, "count": 30, "lng": "tr", "mode": 4, "country": 1,
        "getEmpty": "true", "grMode": 1, "partner": 51, "noFilterBlockBet": "true",
    }
    data = fetch(DOMAINS[0] + "/LineFeed/Get1x2_VZip", params)
    out["matches"] = data
    print("MATCHES:", json.dumps(data)[:800], flush=True)

    with open("probe_1xbet.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, default=str)
    print("yazildi probe_1xbet.json", flush=True)

if __name__ == "__main__":
    main()