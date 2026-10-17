"""Polls Resy availability logged out from a GitHub Actions runner (Azure IP) and publishes
openings to a private ntfy topic that the Mac watcher subscribes to.

Env: NTFY_TOPIC (private detect topic), VENUE_ID, DAYS (comma list), PARTY, INTERVAL,
DURATION (seconds), PROBE=1 to just report statuses."""
import json, os, random, sys, time, urllib.error, urllib.parse, urllib.request

H = {"Authorization": 'ResyAPI api_key="VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"', "Origin": "https://resy.com",
     "Referer": "https://resy.com/", "X-Origin": "https://resy.com",
     "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
venue, party = os.environ.get("VENUE_ID", "60323"), os.environ.get("PARTY", "2")
days = os.environ.get("DAYS", "2026-10-17,2026-10-18,2026-10-19").split(",")
interval, duration = float(os.environ.get("INTERVAL", "2")), float(os.environ.get("DURATION", "60"))
topic = os.environ.get("NTFY_TOPIC", "")


def get(path, params):
    req = urllib.request.Request(f"https://api.resy.com/{path}?{urllib.parse.urlencode(params)}", headers=H)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


ip = urllib.request.urlopen("https://api.ipify.org", timeout=10).read().decode()
print("runner ip", ip, flush=True)
codes, end, sent, refused_streak = {}, time.time() + duration, set(), 0
while time.time() < end:
    t = time.time()
    st, raw = get("4/venue/calendar", {"venue_id": venue, "num_seats": party,
                                       "start_date": min(days), "end_date": max(days)})
    codes[st] = codes.get(st, 0) + 1
    if st == 200:
        refused_streak = 0
        open_days = [d["date"] for d in json.loads(raw).get("scheduled", [])
                     if d["date"] in days and d.get("inventory", {}).get("reservation") == "available"]
        for d in open_days:
            if topic and (d, int(t // 30)) not in sent:  # at most one alert per night per 30s
                sent.add((d, int(t // 30)))
                urllib.request.urlopen(urllib.request.Request(
                    f"https://ntfy.sh/{topic}", data=json.dumps({"day": d, "ip": ip, "t": t}).encode(),
                    method="POST"), timeout=10).close()
                print("published", d, flush=True)
    else:
        refused_streak += 1
        print(time.strftime("%H:%M:%S"), "refused", st, raw[:80], flush=True)
        if refused_streak >= 3 and not os.environ.get("PROBE"):
            # This runner's IP is used up (datacenter IPs get a few dozen reads); the workflow
            # dispatches a replacement job, which lands on a new VM with a new IP
            print("codes", codes, flush=True)
            sys.exit(0)
    time.sleep(max(0, interval * random.uniform(0.85, 1.15) - (time.time() - t)))
print("codes", codes, flush=True)
