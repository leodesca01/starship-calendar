#!/usr/bin/env python3
"""Build an iCalendar feed of Starship launches from Launch Library 2 (The Space Devs).

- Stable UID per launch (LL2 id) -> calendar apps move/update events instead of duplicating.
- Times in UTC -> the calendar app converts to the local time zone.
- Precise T-0 (second/minute/hour) -> timed event with alarms.
  Coarse NET (day/week/month/...) -> all-day placeholder, no alarm.
- Recent past flights are kept (with outcome) so they don't vanish after launch.

Standard library only.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://ll.thespacedevs.com/2.3.0/launches"
QUERY = "search=Starship&mode=normal&limit={limit}"
OUT = os.environ.get("ICS_OUT", "docs/starship.ics")
CAL_NAME = "Starship Launches"
PAST_TO_KEEP = 6
TIMED_PRECISIONS = {0, 1, 2}  # Second, Minute, Hour
DAY_PRECISIONS = {3, 4, 5}  # Morning, Afternoon, Day
STATUS_TAG = {
    "Go": "",
    "TBC": " (TBC)",
    "TBD": " (TBD)",
    "Hold": " (HOLD)",
    "In Flight": " (IN FLIGHT)",
    "Success": " ✅",
    "Failure": " ❌",
    "Partial Failure": " ⚠️",
}


def fetch(path, limit):
    url = f"{API}/{path}/?{QUERY.format(limit=limit)}"
    headers = {"User-Agent": "starship-calendar (GitHub Actions)"}
    token = os.environ.get("LL2_API_KEY")
    if token:
        headers["Authorization"] = f"Token {token}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)["results"]
        except Exception as e:  # noqa: BLE001
            wait = 20 * (attempt + 1)
            print(f"fetch {path} failed ({e}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(f"Could not fetch {path} launches")


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def esc(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line):
    """RFC 5545 line folding at 75 octets, UTF-8 safe."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        limit = 75 if not parts else 74
        if len(cur) + len(b) > limit:
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def fmt(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def event(l, now):
    status = (l.get("status") or {}).get("abbrev") or ""
    prec = (l.get("net_precision") or {}).get("id")
    prec_name = (l.get("net_precision") or {}).get("name") or "unknown"
    net = parse_dt(l["net"])
    name = l["name"].replace("Starship | ", "Starship ")
    timed = prec in TIMED_PRECISIONS
    title = "🚀 " + name + STATUS_TAG.get(status, f" ({status})" if status else "")
    if not timed and status not in ("Success", "Failure", "Partial Failure"):
        title += f" [NET {prec_name}]"

    pad = l.get("pad") or {}
    where = ", ".join(x for x in [pad.get("name"), (pad.get("location") or {}).get("name")] if x)
    vids = l.get("vid_urls") or []
    webcast = vids[0].get("url") if vids else "https://www.spacex.com/launches/"
    mission = (l.get("mission") or {}).get("description") or ""
    updated = parse_dt(l["last_updated"]) if l.get("last_updated") else now
    desc = "\n".join(
        x
        for x in [
            f"Status: {(l.get('status') or {}).get('name', '?')}",
            f"T-0 precision: {prec_name}",
            f"Webcast: {webcast}",
            mission,
            f"Last updated (LL2): {updated:%Y-%m-%d %H:%M} UTC",
            "Data: Launch Library 2 by The Space Devs",
        ]
        if x
    )

    lines = [
        "BEGIN:VEVENT",
        f"UID:{l['id']}@starship-calendar",
        f"DTSTAMP:{fmt(now)}",
        f"LAST-MODIFIED:{fmt(updated)}",
        f"SEQUENCE:{int(updated.timestamp()) // 60}",
        f"SUMMARY:{esc(title)}",
        f"LOCATION:{esc(where)}",
        f"DESCRIPTION:{esc(desc)}",
        f"URL:{webcast}",
        "TRANSP:TRANSPARENT",
    ]
    if timed:
        end = net + timedelta(minutes=90)
        if l.get("window_end"):
            end = max(end, parse_dt(l["window_end"]))
        lines += [f"DTSTART:{fmt(net)}", f"DTEND:{fmt(end)}"]
        if status not in ("Success", "Failure", "Partial Failure"):
            for trig, label in (("-PT1H", "1 hour"), ("-PT10M", "10 minutes")):
                lines += [
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{esc(name)} in {label}",
                    f"TRIGGER:{trig}",
                    "END:VALARM",
                ]
    else:
        d = net.date()
        lines += [
            f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
            f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
        ]
    lines.append("END:VEVENT")
    return lines


def is_starship(l):
    cfg = ((l.get("rocket") or {}).get("configuration") or {}).get("name", "")
    return "starship" in cfg.lower()


def main():
    upcoming = fetch("upcoming", 20)
    time.sleep(2)
    previous = fetch("previous", PAST_TO_KEEP)
    launches = {l["id"]: l for l in previous + upcoming if is_starship(l)}
    now = datetime.now(timezone.utc).replace(microsecond=0)

    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//starship-calendar//LL2//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CAL_NAME}",
        "X-WR-TIMEZONE:UTC",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for l in sorted(launches.values(), key=lambda x: x["net"]):
        out += event(l, now)
    out.append("END:VCALENDAR")

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    body = "\r\n".join(fold(x) for x in out) + "\r\n"
    # Skip rewrite if only DTSTAMP changed -> avoids a commit every hour.
    strip = lambda s: "\n".join(x for x in s.splitlines() if not x.startswith("DTSTAMP:"))
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8", newline="") as f:
            if strip(f.read()) == strip(body):
                print("No changes.")
                return
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    print(f"Wrote {OUT}: {len(launches)} launches")


if __name__ == "__main__":
    main()
