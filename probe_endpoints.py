import requests
API = "https://api.aiscore.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
      "Referer": "https://www.aiscore.com/"}
tests = {
    "matches?date=today&sid=2": API + "/v1/web/api/matches?lang=tr&sport_id=2&date=",
    "today/matches?sid=2": API + "/v1/web/api/today/matches?sid=2&tz=08:00&lang=tr",
    "matches/future?sid=2": API + "/v1/web/api/matches/future?lang=tr&sid=2",
}
for name, u in tests.items():
    try:
        r = requests.get(u, headers=UA, timeout=20)
        c = r.content
        print(name, r.status_code, len(c), c[:120])
    except Exception as e:
        print(name, "ERR", str(e)[:100])