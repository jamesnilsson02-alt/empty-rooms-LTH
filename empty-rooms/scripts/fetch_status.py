#!/usr/bin/env python3
"""
Empty Rooms — hämtar TimeEdit-bokningar för LTH-salar och räknar ut
vilka som är lediga just nu.

TimeEdit-formatet vi jobbar mot har en egenhet: LOCATION-fältet är tomt,
och rumsnamnen ligger istället inbakade i SUMMARY-texten, ofta flera
rum per händelse (t.ex. en gemensam "underhåll"-bokning för fyra
datorsalar samtidigt). Vi extraherar rumsnamn med ett regex-mönster
istället för att lita på LOCATION.
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

# Rumsnamn ser ut som "V:O2", "V:Dator21", "V:Brandsalen", "V:Grupp11" osv.
# Husbokstav + kolon + alfanumeriskt namn.
ROOM_PATTERN = re.compile(r"\b([A-ZÅÄÖ]{1,3}:[A-ZÅÄÖa-zåäö0-9]+)\b")

# Filtrera bort rum-koder som egentligen är "Rumsnummer: V:2501" interna
# fastighetskoder, inte de bokningsbara salnamnen vi bryr oss om.
def extract_room_names(summary: str, known_rooms: set[str]) -> list[str]:
    """Plockar ut vilka av våra kända salar som nämns i SUMMARY-texten."""
    if not summary:
        return []
    found = ROOM_PATTERN.findall(summary)
    # Bara behåll träffar som matchar något av rummen vi faktiskt spårar
    return [r for r in found if r in known_rooms]


def load_room_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def fetch_ics(url: str) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 (EmptyRooms/1.0; LTH student project)"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content


def parse_events(ics_bytes: bytes, known_rooms: set[str]):
    """Returnerar lista av (room, start_dt, end_dt, summary) för relevanta händelser."""
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

        # Heldagshändelser (helgdagar typ "Midsommarafton") har date-objekt
        # istället för datetime — vi struntar i dessa, de är inte rumsbokningar.
        if not isinstance(start, datetime):
            continue

        # Normalisera till svensk tidzon
        if start.tzinfo is None:
            start = start.replace(tzinfo=ZoneInfo("UTC"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=ZoneInfo("UTC"))
        start = start.astimezone(TZ)
        end = end.astimezone(TZ)

        rooms = extract_room_names(summary, known_rooms)
        if not rooms:
            continue

        # Hoppa över "Underhåll och service"-rader som varar 16+ timmar
        # eller flera dagar i sträck — dessa är ofta generella drift-
        # meddelanden snarare än faktiska bokningar som blockerar studier.
        # (Justera/ta bort detta filter om du vill räkna med dem.)
        duration = end - start
        is_long_maintenance = (
            "underhåll" in summary.lower() and duration > timedelta(hours=12)
        )

        for room in rooms:
            events.append({
                "room": room,
                "start": start,
                "end": end,
                "summary": summary.split(",")[0].strip(),  # kort etikett
                "is_maintenance": is_long_maintenance,
            })

    return events


def compute_status(events: list, known_rooms: set[str], now: datetime) -> dict:
    """Bygger statusobjekt per rum: ledig nu / upptagen, samt nästa ändring."""
    status = {room: {"busy_now": False, "current_until": None,
                      "next_event_start": None, "next_event_end": None,
                      "label": None} for room in known_rooms}

    for room in known_rooms:
        room_events = sorted(
            [e for e in events if e["room"] == room and not e["is_maintenance"]],
            key=lambda e: e["start"]
        )

        # Är något pågående just nu?
        ongoing = [e for e in room_events if e["start"] <= now < e["end"]]
        if ongoing:
            # Ta den som slutar senast om flera överlappar
            current = max(ongoing, key=lambda e: e["end"])
            status[room]["busy_now"] = True
            status[room]["current_until"] = current["end"].isoformat()
            status[room]["label"] = current["summary"]

        # Vad händer härnäst (oavsett om upptagen nu eller ej)? Om rummet
        # redan är upptaget vill vi veta vad som händer EFTER den pågående
        # bokningen, inte missa en direkt påföljande bokning.
        reference_end = (
            datetime.fromisoformat(status[room]["current_until"])
            if status[room]["busy_now"] else now
        )
        upcoming = [e for e in room_events if e["start"] >= reference_end]
        if upcoming:
            nxt = min(upcoming, key=lambda e: e["start"])
            status[room]["next_event_start"] = nxt["start"].isoformat()
            status[room]["next_event_end"] = nxt["end"].isoformat()
            if not status[room]["busy_now"]:
                status[room]["label"] = nxt["summary"]

    return status


def main():
    base = Path(__file__).parent.parent
    config = load_room_config(base / "data" / "rooms_config.json")
    known_rooms = set(config["rooms"].keys())

    all_events = []
    for source in config["ics_sources"]:
        try:
            ics_bytes = fetch_ics(source["url"])
            events = parse_events(ics_bytes, known_rooms)
            all_events.extend(events)
        except Exception as e:
            print(f"Fel vid hämtning av {source.get('name', source['url'])}: {e}",
                  file=sys.stderr)

    now = datetime.now(TZ)
    status = compute_status(all_events, known_rooms, now)

    output = {
        "generated_at": now.isoformat(),
        "building": config.get("building", ""),
        "rooms": {
            room: {
                **meta,
                **status[room],
            }
            for room, meta in config["rooms"].items()
        },
    }

    out_path = base / "data" / "status.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Skrev status för {len(known_rooms)} salar till {out_path}")


if __name__ == "__main__":
    main()
