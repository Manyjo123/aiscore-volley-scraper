import json, requests

HEADERS = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
API = "https://api.aiscore.com"
test_ids = json.load(open("test_ids.json", "r"))
out = {}
for mid in test_ids:
    r = requests.get(f"{API}/v1/web/api/match/data?lang=tr&match_id={mid}", headers=HEADERS, timeout=20)
    if r.status_code != 200:
        out[mid] = f"HTTP {r.status_code}"
        continue
    try:
        import blackboxprotobuf
        msg, _ = blackboxprotobuf.decode_message(r.content)
        o = msg.get("15", {})
        if isinstance(o, str):
            import ast
            try:
                o = ast.literal_eval(o)
            except Exception as e:
                out[mid] = "literal_eval HATA " + str(e)[:80]
                continue
        sc = {}
        if isinstance(o, dict):
            f = o.get("1", {}).get("108", {})
            for k in ("1", "2", "3", "4", "5", "6"):
                v = f.get(k)
                if isinstance(v, bytes):
                    sc["set" + k] = list(v)
            out[mid] = {
                "home": (o.get("6") or {}).get("6", "?"),
                "away": (o.get("7") or {}).get("6", "?"),
                "league": (o.get("4") or {}).get("5", "?"),
                "scores": sc,
            }
        else:
            out[mid] = "no 15 field"
    except Exception as e:
        out[mid] = "decode HATA " + str(e)[:80]
json.dump(out, open("probe_data_out.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1)[:3000])