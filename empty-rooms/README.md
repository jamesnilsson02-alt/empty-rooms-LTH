# Empty Rooms

Visar vilka övningssalar och datorsalar i V-huset på LTH som faktiskt
är lediga just nu — så man slipper gå runt och leta plats att plugga
i, särskilt jobbigt under tentaperioder.

Datan kommer från LTH:s publika TimeEdit-schema. Om TimeEdit säger att
en sal inte är bokad just nu är den med stor sannolikhet faktiskt tom
och pluggbar (till skillnad från t.ex. grupprum, som är "först till
kvarn" och inte syns korrekt i schemat).

## Hur det funkar

```
.github/workflows/update-status.yml   Manuellt triggad workflow (ingen bakgrundskörning)
scripts/fetch_status.py               Hämtar TimeEdit-ics, räknar ut status per sal
data/rooms_config.json                Vilka salar som spåras + ics-källa
data/status.json                      Senaste beräknade statusen (skrivs av scriptet)
docs/index.html                       Sidan som visar statusen (GitHub Pages)
```

**Flödet:** Du triggar workflow:n manuellt (Actions-fliken → "Uppdatera
salstatus" → "Run workflow") → scriptet hämtar färsk data från TimeEdit
→ skriver `data/status.json` → committar tillbaka till repot →
GitHub Pages-sidan läser filen och visar status.

Ingen schemaläggning, inget som kör i bakgrunden i onödan — du
uppdaterar när du faktiskt vill veta läget.

## Sätta upp GitHub Pages

1. Gå till repots **Settings → Pages**
2. Under "Build and deployment", välj **Deploy from a branch**
3. Branch: `main`, mapp: `/docs`
4. Spara — sidan blir tillgänglig på `https://<ditt-användarnamn>.github.io/empty-rooms/`

## Lägga till fler salar eller hus

Redigera `data/rooms_config.json`:
- Lägg till fler `ics_sources` om du vill spåra fler hus (varje TimeEdit-
  sökning genererar en egen `.ics`-länk)
- Lägg till rum under `"rooms"` med rätt namn (måste matcha hur rummet
  skrivs i TimeEdits SUMMARY-fält, t.ex. `"V:O2"`)

## Begränsningar

- TimeEdit-länken har ett datumintervall inbakat — om "rullande" valdes
  vid export bör det fortsätta fungera över tid, annars kan länken
  behöva förnyas efter några månader.
- Underhållsbokningar (typ "Ominstallation, skärmbyte") som varar 12+
  timmar filtreras bort automatiskt i `fetch_status.py`, eftersom de
  ofta är generella driftnoteringar snarare än faktiska hinder. Justera
  `is_long_maintenance`-logiken om det inte stämmer i praktiken.
- Datan är aldrig mer aktuell än senaste gången workflow:n kördes —
  sidan visar "senast uppdaterad" så du ser hur färsk statusen är.
