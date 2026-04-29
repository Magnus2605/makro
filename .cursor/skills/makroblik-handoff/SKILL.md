---
name: makroblik-handoff
description: Makroblik handoff + mini-eksempler (DST POST, series_payload, stub). Brug ved ny chat, onboarding, eller når du tilføjer indikatorer/API-kald.
---

# Makroblik — hurtig overdragelse til ny chat

## Hvad repoet er
Single-page **makro-dashboard** for dansk økonomi: `GET /api/macro` leverer grupperede indikatorer; `public/app.js` tegner kort. Backend er **`server.py`** (stdlib HTTP-server, ingen framework).

## Før du koder: læs (rækkefølge)
1. `.cursor/rules/makroblik-overview.mdc` — formål, filer, DST-noter, cache.
2. `.cursor/rules/restart-python-server.mdc` — genstart efter ændringer.
3. **`README.md`** — kørsel (`npm start` / `python server.py`), miljøvariabler, deploy (Render).
4. I `server.py`: `GROUP_DEFS`, `SERIES_CONFIG`, `build_live_payload()`, relevant `fetch_*`.

## Skabelon brugeren kan indsætte i ny chat (kopiér/udfyld)
```markdown
Repo: makro (Makroblik)
Sti: <absolut sti til git/makro>
Stack: Python server.py + public/ (statisk UI), API /api/macro
Aktuel opgave: <1–3 sætninger>
Seneste beslutninger: <fx "boligbyrde = FU12/FU19", "aldersfordeling = FU18">
Åbne filer / fokus: <valgfrit>
```

## Nyt kort (korteste sti)
1. `GROUP_DEFS` → id med i gruppen (`INDICATOR_IDS` følger automatisk).
2. `SERIES_CONFIG` → metadata + DST-opslag.
3. `build_live_payload` → kun hvis ikke ren `fetch_dst_series`.
4. `_stub_series_payload` → altid for nyt id.
5. Frontend kun ved **nye felter** ud over standardkort (skabelon + `renderIndicator`).

## Mini-eksempler (sandheden er altid `server.py`)

**DST — POST-body** (samme som `fetch_json(DST_API_URL, …)` i `fetch_dst_series`). Tabel + variabelkoder skal matche **din** tabel i Statistikbanken — her PRIS01 som mønster:

```json
{
  "table": "PRIS01",
  "format": "JSONSTAT",
  "variables": [
    { "code": "VAREGR", "values": ["000000"] },
    { "code": "ENHED", "values": ["300"] },
    { "code": "Tid", "values": ["*"] }
  ]
}
```

**`SERIES_CONFIG`-mønster** (ud over `table` / `variables` findes label, unit, explanation, sourceLabel, goodDirection, osv. — kopier et eksisterende nøglepar som `inflation` eller `unemployment`):

- `table`: StatBank-tabel-id (streng).
- `variables`: liste af `{ "code": "<dimension>", "values": ["…"] }`; brug `"*"` på tid for alle perioder (som koden forventer).

**`series_payload` efter fetch** (hvad `build_indicator` forventer fra standard-DST): mindst `updated` (streng), `series` som `[{ "period": "2024M01", "value": 1.2 }, …]`, `sourceLabel`. Valgfrit: `displayTable`, `externalHref`, `linkLabel`; special: `ageBreakdown` + `breakdownYear` for FU18-kort.

**Stub til fallback** (simpelt DST-kort — default-gren i `_stub_series_payload`): returnér samme nøgler som live (`updated`, `series`, `sourceLabel`, gerne `displayTable`), så cache-validering og UI ikke knækker.

**Ikke-DST (OMX):** `fetch_omx_index_series()` — Yahoo chart JSON, ticker fra `STOCK_SENTIMENT_TICKER`; payload får typisk `externalHref` / `linkLabel`. Tilføj ikke nye Yahoo-kald uden samme fejlhåndtering som i repoet.

## Små verifikationer (billigere end at gætte)
- Kør fra repo-roden (via HTTP, ikke kun Python-import):
  - `python -c "import json,urllib.request; d=json.loads(urllib.request.urlopen('http://127.0.0.1:3000/api/macro',timeout=30).read().decode('utf-8')); print('live', d.get('live'), 'indicators', len(d.get('indicators',[])))"` — forvent **live True** og antal indikatorer = `len(INDICATOR_IDS)` (som i backendens payload). Hvis den fejler på timeout lige efter genstart, så kør kommandoen igen (serveren kan være ved at hente DST første gang).
- Tjek at ny indikator er i **`GROUP_DEFS`**, **`SERIES_CONFIG`**, **`build_live_payload`**-gren (eller `fetch_dst_series`), og **`_stub_series_payload`** hvis fallback skal virke.

## Typiske fejl at undgå
- Nye DST-tabeller uden at matche **dimension-id’er** præcist → 400 fra API.
- Glemme **stub** for nyt indikator-id → fallback/cache mismatch.
- Ændre server/`public/` uden **genstart** → bruger ser gammel kode.
