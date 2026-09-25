#!/usr/bin/env python3
"""Canlı maçlarda oranlar nerede? odds/list yanıtını ham haliyle incele."""
import io, sys, requests
import blackboxprotobuf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
API = "https://api.aiscore.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
MIDS = ["9gkldiwopy0amqx", "vmqylio8meoigk9", "ezk95izy6y8t17n"]

for mid in MIDS:
    r = requests.get(f"{API}/v1/m/api/match/odds/list?match_id={mid}&code=&platform=1", headers=HEADERS, timeout=20)
    print("====", mid, "HTTP", r.status_code, "len", len(r.content))
    if len(r.content) < 60:
        print("  boş yanıt")
        continue
    # hamda oran değerleri var mı (1.xx formatı)
    t = r.content.decode("latin1", "replace")
    import re
    fs = re.findall(r"1\.\d{2,3}", t)
    print("  ham oran adayları:", fs[:12])
    try:
        msg, _ = blackboxprotobuf.decode_message(r.content)
        # üst düzey alanları
        print("  üst keyler:", list(msg.keys())[:12])
        f15 = msg.get("15")
        print("  15 tipi:", type(f15).__name__, "| keys:", list(f15.keys())[:12] if isinstance(f15, dict) else "-")
    except Exception as e:
        print("  DECODE ERR", str(e)[:80])