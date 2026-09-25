import requests
import blackboxprotobuf
import json
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API = "https://api.aiscore.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
      "Referer": "https://www.aiscore.com/"}


def b2s(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


def clean(o):
    if isinstance(o, dict):
        return {k: clean(b2s(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(b2s(v)) for v in o]
    return b2s(o)


for name, url in {
    "today": API + "/v1/web/api/today/matches?sid=10&tz=08:00&lang=tr",
    "future": API + "/v1/web/api/matches/future?lang=tr&sid=10",
}.items():
    try:
        r = requests.get(url, headers=UA, timeout=20)
        msg, _ = blackboxprotobuf.decode_message(r.content)
        msg = clean(msg)
        json.dump(msg, open(f"probe_{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        s = json.dumps(msg, ensure_ascii=False)[:1800]
        print(f"=== {name}: {len(r.content)} byte")
        print(s)
    except Exception as e:
        print(name, "ERR", str(e)[:150])