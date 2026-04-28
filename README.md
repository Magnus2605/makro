# Makrotool (Makroblik)

Lille webapp med danske makronøgletal fra [Danmarks Statistik](https://www.dst.dk/) (StatBank API). Backend er **Python** (`server.py`); frontend ligger i `public/`.

## Krav

- **Python 3.10+** (til `http.server` og API-mod-DST)
- **Node.js** (valgfrit — kun til `npm start`, som starter Python)

## Kørsel

```bash
# Anbefalet (starter Python via server.js)
npm start
```

```bash
# Eller direkte — samme adfærd
python server.py
```

Åbn derefter [http://127.0.0.1:3000/](http://127.0.0.1:3000/) (eller den port du har sat i miljøet).

## Konfiguration

Kopiér `.env.example` til `.env` og justér ved behov:

| Variabel | Betydning |
|----------|-----------|
| `HOST` | Adresse serveren lytter på (`127.0.0.1` lokalt; `0.0.0.0` hvis den skal tilgås fra netværk — kombiner med firewall) |
| `PORT` | Lokal serverport (standard `3000`) |
| `CACHE_TTL_SECONDS` | Cache for `/api/macro` i sekunder (standard `21600` = 6 timer) |
| `DST_API_URL` | Valgfri — kun hvis du skal pege et andet sted hen end standard StatBank-API |
| `PYTHON` | Valgfri — hvilken Python-binary `npm start` bruger (fx `py -3.11` på Windows) |

Der kræves **ingen API-nøgle** til de åbne DST-data.

## Efter kodeændringer i `server.py`

Genstart processen, der kører `server.py`, sændringer i hukommelsen træder først i kraft efter genstart.

## Deploy til gratis hosting (kollega kan åbne i browser)

**Netlify / ren statisk hosting** passer ikke her: siden behøver **Python-backend** til `/api/macro` mod Danmarks Statistik. Du skal bruge en **container-/process-host** (fx Render, Railway, Fly).

### Anbefalet: [Render](https://render.com) (gratis Web Service)

1. Push dette repo til **GitHub** (eller GitLab).
2. Opret konto på Render → **New** → **Blueprint** → tilslut repo og peg på `render.yaml`, **eller** **Web Service** med:
   - **Runtime:** Python 3.11
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `python server.py`
   - **Miljøvariabler:** `HOST` = `0.0.0.0` (Render sætter `PORT` selv — lad den være).
3. Efter deploy får du en URL som `https://makrotool-xxxx.onrender.com`.

**Vigtigt på Free-plan:** servicen **sovner** efter en periode uden trafik; første besøg efter pausen kan tage **30–60 sek**. Det er normalt på gratis tier.

### Hurtig demo uden cloud (valgfrit)

Med [ngrok](https://ngrok.com/) eller lign.: kør `python server.py` lokalt og eksponér port 3000 — du får en midlertidig URL til kollega (ingen permanent drift).
