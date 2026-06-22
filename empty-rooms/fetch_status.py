#!/usr/bin/env python3
"""
Empty Rooms — hämtar TimeEdit-bokningar för LTH-salar och exporterar
hela dagens bokningslista per rum, så att JavaScript kan räkna ut
optimal sal, tidslinje och aktuell status direkt i browsern.
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar

TZ = ZoneInfo("Europe/Stockholm")
ROOM_PATTERN = re.compile(r"\b([A-ZÅÄÖ]{1,3}:[A-ZÅÄÖa-zåäö0-9]+)\b")


def extract_room_names(summary: str, known_rooms: set) -> list:
    if not summary:
        return []
    found = ROOM_PATTERN.findall(summary)
    return [r for r in found if r in known_rooms]


def load_room_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def fetch_ics(url: str) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 (EmptyRooms/1.0; LTH student project)"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content


def parse_events(ics_bytes: bytes, known_rooms: set, today: datetime) -> list:
    """Returnerar dagens händelser som dicts med room, start, end, label."""
    cal = Calendar.from_ical(ics_bytes)
    events = []

    for component in cal.walk("VEVENT"):
        summary = str(component.get("SUMMARY", ""))
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")

        if dtstart is None or dtend is None:
            continue

        start = dtstart.dt
        end = dtend.dt

        # Heldagshändelser (helgdagar) har date-objekt, hoppa över
        if not isinstance(start, datetime):
            continue

        # Normalisera till svensk tid
        if start.tzinfo is None:
            start = start.replace(tzinfo=ZoneInfo("UTC"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=ZoneInfo("UTC"))
        start = start.astimezone(TZ)
        end = end.astimezone(TZ)

        # Bara dagens händelser
        if start.date() != today.date() and end.date() != today.date():
            continue

        rooms = extract_room_names(summary, known_rooms)
        if not rooms:
            continue

        # Filtrera bort långa underhållsbokningar
        duration = end - start
        if "underhåll" in summary.lower() and duration > timedelta(hours=12):
            continue

        # Kort läsbar etikett — första segmentet i SUMMARY
        parts = [p.strip() for p in summary.split(",")]
        label = parts[0].replace("Aktivitet: ", "").strip()

        for room in rooms:
            events.append({
                "room": room,
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
                "label": label,
            })

    return events


def main():
    base = Path(__file__).parent.parent
    config = load_room_config(base / "data" / "rooms_config.json")
    known_rooms = set(config["rooms"].keys())

    now = datetime.now(TZ)
    all_events = []

    for source in config["ics_sources"]:
        try:
            ics_bytes = fetch_ics(source["url"])
            events = parse_events(ics_bytes, known_rooms, now)
            all_events.extend(events)
            print(f"Hämtade {len(events)} händelser från {source.get('name', 'okänd källa')}")
        except Exception as e:
            print(f"Fel: {e}", file=sys.stderr)

    # Bygg output: metadata + rumsinfo + dagens bokningar per rum
    rooms_out = {}
    for room, meta in config["rooms"].items():
        bookings = sorted(
            [e for e in all_events if e["room"] == room],
            key=lambda e: e["start"]
        )
        rooms_out[room] = {
            **meta,
            "bookings": [{"start": b["start"], "end": b["end"], "label": b["label"]}
                         for b in bookings],
        }

    output = {
        "generated_at": now.isoformat(),
        "generated_date": now.strftime("%Y-%m-%d"),
        "building": config.get("building", ""),
        "rooms": rooms_out,
    }

    out_path = base / "data" / "status.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Skrev status för {len(known_rooms)} salar till {out_path}")


if __name__ == "__main__":
    main()
