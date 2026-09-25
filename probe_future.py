import requests
import blackboxprotobuf
import json
import datetime
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API = "https://api.aiscore.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
      "Referer": "https://www.aiscore.com/"}


def dec(content):
    try:
        msg, _ = blackboxprotobuf.decode_message(content)
        return msg
    except Exception as e:
        return {"_err": str(e)}


def norm(v):
    s = str(v)
    return s[2:-1] if s.startswith("b'") and s.endswith("'") else s


# 1) gelecek maclar
out = {}
for name, url in {
    "future": API + "/v1/web/api/matches/future?lang=tr&sid=2",
    "today": API + "/v1/web/api/today/matches?sid=2&tz=08:00&lang=tr",
}.items():
    try:
        r = requests.get(url, headers=UA, timeout=20)
        m = dec(r.content)
        json.dump(m, open(f"probe_{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"=== {name}: {len(r.content)} byte -> probe_{name}.json")
        print(json.dumps(m, ensure_ascii=False)[:1500])
    except Exception as e:
        print(name, "ERR", str(e)[:100])