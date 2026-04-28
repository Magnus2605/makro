from __future__ import annotations

import copy
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


def _load_optional_dotenv() -> None:
    """Indlæs .env fra projektroden uden ekstra pip-afhængigheder."""
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


_load_optional_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    stripped = raw.strip()
    return stripped if stripped else default


PORT = _env_int("PORT", 3000)
if not (1 <= PORT <= 65535):
    PORT = 3000

HOST = _env_str("HOST", "127.0.0.1")
if not HOST:
    HOST = "127.0.0.1"

PUBLIC_DIR = Path(__file__).parent / "public"


def statbank_define_url(table_id: str) -> str:
    """Dyb link til tabel i Statistikbankens Define-visning."""
    return (
        "https://www.statistikbanken.dk/statbank5a/SelectVarVal/Define.asp?"
        + urlencode({"Maintable": table_id, "PLanguage": "0"})
    )
DST_API_URL = _env_str("DST_API_URL", "https://api.statbank.dk/v1/data")
CACHE_TTL_SECONDS = max(0, _env_int("CACHE_TTL_SECONDS", 60 * 60 * 6))

# OMX-markedsindeks via Yahoo Finance (standard ^OMXC25). Kan skiftes via miljøvariabel.
STOCK_SENTIMENT_TICKER = _env_str("STOCK_SENTIMENT_TICKER", "^OMXC25")


SERIES_CONFIG = {
    "inflation": {
        "table": "PRIS01",
        "variables": [
            {"code": "VAREGR", "values": ["000000"]},
            {"code": "ENHED", "values": ["300"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "down",
        "label": "Inflation",
        "unit": "%",
        "importance": "H\u00f8j",
        "explanation": (
            "Inflation viser hvor hurtigt priserne stiger i forhold til samme m\u00e5ned \u00e5ret f\u00f8r. "
            "N\u00e5r inflationen falder, bliver presset p\u00e5 husholdningernes budgetter typisk mindre."
        ),
        "sourceLabel": "Danmarks Statistik, PRIS01",
    },
    "unemployment": {
        "table": "AKU101K",
        "variables": [
            {"code": "BESKSTATUS", "values": ["LPCT"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "down",
        "label": "AKU-ledighed",
        "unit": "%",
        "importance": "H\u00f8j",
        "explanation": (
            "AKU-ledighed er Danmarks Statistiks m\u00e5l for hvor stor en del af arbejdsstyrken der "
            "er ledig. N\u00e5r ledigheden stiger, peger det ofte p\u00e5 et arbejdsmarked med mindre fart."
        ),
        "sourceLabel": "Danmarks Statistik, AKU101K",
    },
    "gdp-growth": {
        "table": "NKN1",
        "variables": [
            {"code": "TRANSAKT", "values": ["B1GQK"]},
            {"code": "PRISENHED", "values": ["L_V"]},
            {"code": "S\u00c6SON", "values": ["Y"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "label": "BNP-v\u00e6kst",
        "unit": "%",
        "importance": "H\u00f8j",
        "explanation": (
            "Her ser vi realv\u00e6kst i BNP i forhold til forrige kvartal. Positiv v\u00e6kst betyder, "
            "at \u00f8konomien udvider sig, mens svag eller negativ v\u00e6kst peger mod afmatning."
        ),
        "sourceLabel": "Danmarks Statistik, NKN1",
    },
    "consumer-confidence": {
        "table": "FORV1",
        "variables": [
            {"code": "INDIKATOR", "values": ["F1"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "chartMode": "line",
        "label": "Forbrugertillid",
        "unit": "%",
        "scaleUnit": "%",
        "includeZero": True,
        "importance": "Mellem",
        "explanation": (
            "Forbrugertilliden viser, hvordan danskerne ser på økonomien lige nu og lidt frem. "
            "Når den stiger, peger det ofte på mere optimisme og mindre forsigtighed."
        ),
        "sourceLabel": "Danmarks Statistik, FORV1",
    },
    "new-car-registrations-household": {
        "table": "BIL5",
        "variables": [
            {"code": "BILTYPE", "values": ["4000101004"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "chartMode": "line",
        "label": "Nyreg. personbiler (husholdninger)",
        "unit": "stk.",
        "scaleUnit": "",
        "includeZero": True,
        "importance": "Mellem",
        "explanation": (
            "DST's kategori \u00abPersonbiler i husholdningerne\u00bb: nyregistreringer, hvor ejeren i "
            "motorregistret (DMR) er klassificeret som privat husholdning \u2014 typisk personligt bilk\u00f8b. "
            "Danmarks Statistik bruger opdelingen til bl.a. at belyse husholdningernes forbrug og "
            "investeringer i k\u00f8ret\u00f8jer (jf. dokumentationen til bilregistret/BIL5)."
        ),
        "sourceLabel": "Danmarks Statistik, BIL5",
    },
    "new-car-registrations-business": {
        "table": "BIL5",
        "variables": [
            {"code": "BILTYPE", "values": ["4000101005"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "chartMode": "line",
        "label": "Nyreg. personbiler (erhverv)",
        "unit": "stk.",
        "scaleUnit": "",
        "includeZero": True,
        "importance": "Mellem",
        "explanation": (
            "DST's kategori \u00abPersonbiler i erhverv\u00bb: nyregistreringer, hvor ejeren ikke er en privat "
            "husholdning, men fx virksomhed eller anden erhvervsakt\u00f8r \u2014 herunder typisk firmabiler og "
            "vognpark. Serien supplerer husholdningerne og bruges bl.a. til erhvervenes investeringer i "
            "k\u00f8ret\u00f8jer (samme kilde og dokumentation som ovenfor)."
        ),
        "sourceLabel": "Danmarks Statistik, BIL5",
    },
    "retail-sales": {
        "table": "DETA212A",
        "variables": [
            {"code": "BRANCHEDB25UDVALG", "values": ["G47"]},
            {"code": "INDEKSTYPE", "values": ["SMAENGDE"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "chartMode": "line",
        "label": "Detailsalg",
        "unit": "Indeks",
        "scaleUnit": "",
        "importance": "Mellem",
        "explanation": (
            "Detailsalg viser, hvordan omsætningen i detailhandlen bevæger sig. Det er et godt "
            "signal for, hvor meget husholdningerne faktisk køber i butikkerne."
        ),
        "sourceLabel": "Danmarks Statistik, DETA212A",
    },
    "industry-production": {
        "table": "IPOP21",
        "variables": [
            {"code": "SÆSON", "values": ["SÆSON"]},
            {"code": "BRANCHEDB25UDVALG", "values": ["C"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "chartMode": "line",
        "label": "Industri",
        "unit": "Indeks",
        "scaleUnit": "Indeks",
        "importance": "Mellem",
        "explanation": (
            "Industriproduktionen viser, om fabriks- og industrivirksomhederne producerer mere "
            "eller mindre over tid. Det er et godt signal for den tungere del af økonomien."
        ),
        "sourceLabel": "Danmarks Statistik, IPOP21",
    },
    "housing-prices": {
        "table": "EJ56",
        "variables": [
            {"code": "OMRÅDE", "values": ["000"]},
            {"code": "EJENDOMSKATE", "values": ["0111"]},
            {"code": "TAL", "values": ["310"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "chartMode": "line",
        "label": "Boligpriser",
        "unit": "%",
        "scaleUnit": "%",
        "importance": "Mellem",
        "explanation": (
            "Boligpriserne fortæller, hvordan prisniveauet på enfamiliehuse udvikler sig fra "
            "kvartal til kvartal. Det siger noget om både boligmarked og husholdningernes formue."
        ),
        "sourceLabel": "Danmarks Statistik, EJ56",
    },
    "housing-burden-income": {
        "table": "FU12",
        "goodDirection": "down",
        "chartMode": "line",
        "label": "Boligbyrde (andel af indkomst, FU12/FU19)",
        "unit": "%",
        "scaleUnit": "%",
        "includeZero": True,
        "importance": "Mellem",
        "explanation": (
            "Fra Forbrugsunders\u00f8gelsen (FU-grupperne): COICOP-gruppe 04 \u00abBolig, vand, elektricitet, gas og "
            "andet br\u00e6ndsel\u00bb (kr. pr. gennemsnitshusstand, FU12, l\u00f8bende priser) sat i forhold til "
            "disponibel indkomst \u00abM\u00bb (FU19, linje for disponibel indkomst). Det er stadig "
            "gennemsnitstal for husstande \u2014 ikke median \u2014 men det er mikro-/survey-baseret og typisk "
            "t\u00e6ttere p\u00e5 \u00abbudget-andele\u00bb end nationalregnskabet. Opdateres \u00e5rligt."
        ),
        "sourceLabel": "Danmarks Statistik (FU12 + FU19)",
    },
    "housing-share-age-fu18": {
        "table": "FU18",
        "goodDirection": "down",
        "chartMode": "line",
        "label": "Boligandel af forbruget (efter alder)",
        "unit": "%",
        "scaleUnit": "%",
        "includeZero": True,
        "historyPoints": 12,
        "importance": "Mellem",
        "explanation": (
            "Fra Forbrugsunders\u00f8gelsen (FU18): andelen af det samlede forbrug (COICOP 00), der bruges til bolig og "
            "energi (COICOP 04), opgjort pr. aldersgruppe for hovedpersonen og som gennemsnit over alle husstande. "
            "Det er forbrugets fordeling \u2014 ikke bolig ift. indkomst som FU12/FU19-kortet. Grafen viser "
            "udviklingen for gennemsnitshusstanden; tabellen viser seneste \u00e5rs opdeling efter alder."
        ),
        "sourceLabel": "Danmarks Statistik, FU18",
    },
    "housing-debt-families": {
        "table": "EJERFOF1",
        "variables": [
            {"code": "FORMGLD", "values": ["135"]},
            {"code": "BOPKOM", "values": ["000"]},
            {"code": "ENHED", "values": ["115"]},
            {"code": "FAMTYPE", "values": ["A0"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "valueDivisor": 1000,
        "goodDirection": "down",
        "chartMode": "line",
        "label": "Familiers boligg\u00e6ld",
        "unit": "mia. kr.",
        "scaleUnit": "",
        "includeZero": False,
        "importance": "Mellem",
        "explanation": (
            "Samlet g\u00e6ld knyttet til fast ejendom for familier i hele landet (komponent B i "
            "EJERFOF1), opgjort i ejendoms- og tinglysningsregistre — prim\u00e6rt realkredit- og "
            "bankg\u00e6ld med pant i bolig. Vist i milliarder kr.; opdateres \u00e5rligt med forbehold "
            "for senere revision af seneste \u00e5r."
        ),
        "sourceLabel": "Danmarks Statistik, EJERFOF1",
    },
    "realkredit-outstanding-hh": {
        "table": "DNRUURI",
        "variables": [
            {"code": "DATA", "values": ["AL50GNSB"]},
            {"code": "INDSEK", "values": ["1430"]},
            {"code": "VALUTA", "values": ["Z01"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "valueDivisor": 1000,
        "goodDirection": "down",
        "chartMode": "line",
        "label": "Realkredit (udest\u00e5ende, hush.)",
        "unit": "mia. kr.",
        "scaleUnit": "",
        "historyPoints": 36,
        "includeZero": False,
        "importance": "Mellem",
        "explanation": (
            "Nominelt udest\u00e5ende indenlandske realkreditudl\u00e5n til husholdninger (sektor 1430: "
            "l\u00f8nmodtagere, pensionister mv.), alle valutaer. Fra Nationalbankens/Danmarks Statistiks "
            "f\u00e6lles Statistikbank (DNRUURI) — viser udviklingen i boligfinansiering via realkredit over tid."
        ),
        "sourceLabel": "Nationalbanken / Statistikbanken, DNRUURI",
    },
    "interest-rate": {
        "table": "MPK3",
        "variables": [
            {"code": "TYPE", "values": ["5500602021"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "down",
        "chartMode": "line",
        "label": "Rente",
        "unit": "%",
        "scaleUnit": "%",
        "importance": "Mellem",
        "explanation": (
            "Renten viser de korte danske markeds- og pengepolitiske renter. Højere renter gør "
            "det typisk dyrere at låne og køler økonomien ned."
        ),
        "sourceLabel": "Danmarks Statistik, MPK3",
    },
    "business-confidence": {
        "table": "ETILLID",
        "variables": [
            {"code": "INDIKATOR", "values": ["TE"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "chartMode": "line",
        "label": "Erhvervstillid",
        "unit": "Indeks",
        "scaleUnit": "",
        "includeZero": True,
        "importance": "Mellem",
        "explanation": (
            "Erhvervstilliden samler tilliden i industri, bygge og anlæg, detail og service. "
            "Værdien 100 svarer til historisk middel; over 100 betyder typisk mere optimisme."
        ),
        "sourceLabel": "Danmarks Statistik, ETILLID",
    },
    "export-growth": {
        "table": "NKN1",
        "variables": [
            {"code": "TRANSAKT", "values": ["P6D"]},
            {"code": "PRISENHED", "values": ["L_V"]},
            {"code": "SÆSON", "values": ["Y"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "label": "Eksport (vækst)",
        "unit": "%",
        "importance": "Mellem",
        "explanation": (
            "Viser realvækst i eksport af varer og tjenester i forhold til forrige kvartal. "
            "Højere vækst her understøtter ofte aktivitet og beskæftigelse i eksponerede sektorer."
        ),
        "sourceLabel": "Danmarks Statistik, NKN1",
    },
    "private-consumption": {
        "table": "NKN1",
        "variables": [
            {"code": "TRANSAKT", "values": ["P31S14D"]},
            {"code": "PRISENHED", "values": ["L_V"]},
            {"code": "SÆSON", "values": ["Y"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "label": "Husholdningsforbrug",
        "unit": "%",
        "importance": "Mellem",
        "explanation": (
            "Husholdningernes forbrugsudgifter er en stor del af efterspørgslen i økonomien. "
            "Stigninger peger typisk på mere aktivitet i detail og tjenester."
        ),
        "sourceLabel": "Danmarks Statistik, NKN1",
    },
    "fixed-investment": {
        "table": "NKN1",
        "variables": [
            {"code": "TRANSAKT", "values": ["P51GD"]},
            {"code": "PRISENHED", "values": ["L_V"]},
            {"code": "SÆSON", "values": ["Y"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "label": "Faste investeringer",
        "unit": "%",
        "importance": "Mellem",
        "explanation": (
            "Faste bruttoinvesteringer dækker fx maskiner, byggeri og udstyr. Det siger noget om, "
            "hvor meget virksomhederne tør binde kapital for fremtidig produktion."
        ),
        "sourceLabel": "Danmarks Statistik, NKN1",
    },
    "import-growth": {
        "table": "NKN1",
        "variables": [
            {"code": "TRANSAKT", "values": ["P7K"]},
            {"code": "PRISENHED", "values": ["L_V"]},
            {"code": "S\u00c6SON", "values": ["Y"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "label": "Import (v\u00e6kst)",
        "unit": "%",
        "importance": "Mellem",
        "explanation": (
            "Import af varer og tjenester viser, hvor meget Danmark k\u00f8ber fra udlandet "
            "m\u00e5lt som realv\u00e6kst kvartal til kvartal. Det p\u00e5virker b\u00e5de virksomhedernes "
            "indk\u00f8b og husholdningernes forbrug af importerede varer."
        ),
        "sourceLabel": "Danmarks Statistik, NKN1",
    },
    "government-consumption": {
        "table": "NKN1",
        "variables": [
            {"code": "TRANSAKT", "values": ["P3S13D"]},
            {"code": "PRISENHED", "values": ["L_V"]},
            {"code": "S\u00c6SON", "values": ["Y"]},
            {"code": "Tid", "values": ["*"]},
        ],
        "goodDirection": "up",
        "label": "Offentligt forbrug",
        "unit": "%",
        "importance": "Mellem",
        "explanation": (
            "Det offentlige forbrug d\u00e6kker fx sundhed, undervisning og administration. "
            "St\u00f8rre v\u00e6kst her betyder typisk mere aktivitet i den del af \u00f8konomien, "
            "som kommuner, regioner og stat driver."
        ),
        "sourceLabel": "Danmarks Statistik, NKN1",
    },
    "stock-sentiment": {
        "table": "Yahoo Finance",
        "goodDirection": "up",
        "chartMode": "line",
        "label": "OMX C25",
        "unit": "Indeks",
        "scaleUnit": "",
        "historyPoints": 260,
        "includeZero": False,
        "importance": "Mellem",
        "explanation": (
            "OMX Copenhagen 25 er et indeks for de 25 mest handlede aktier p\u00e5 Nasdaq Copenhagen. "
            "Her vises indeksets niveau (daglig lukkekurs) over ca. det seneste \u00e5r fra Yahoo Finance. "
            "Det er markedsinformation, ikke investeringsr\u00e5dgivning."
        ),
        "sourceLabel": "Yahoo Finance",
    },
}


GROUP_DEFS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("overview", "Samlet \u00f8konomi", ("inflation", "unemployment", "gdp-growth")),
        (
        "demand",
        "Forbrug og offentlig sektor",
        (
            "consumer-confidence",
            "new-car-registrations-household",
            "new-car-registrations-business",
            "private-consumption",
            "retail-sales",
            "government-consumption",
        ),
    ),
    ("business", "Erhverv og investering", ("business-confidence", "industry-production", "fixed-investment")),
    ("trade", "Handel med udlandet", ("export-growth", "import-growth")),
        (
        "housing",
        "Bolig og finansiering",
        (
            "housing-prices",
            "housing-burden-income",
            "housing-share-age-fu18",
            "housing-debt-families",
            "realkredit-outstanding-hh",
            "interest-rate",
        ),
    ),
    ("markets", "Markeder", ("stock-sentiment",)),
)


INDICATOR_IDS: tuple[str, ...] = tuple(
    indicator_id for _, _, ids in GROUP_DEFS for indicator_id in ids
)


def fetch_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_jsonstat_series(dataset: dict[str, object]) -> list[dict[str, object]]:
    dimensions = dataset["dimension"]
    time_dimension = dimensions["Tid"]["category"]["index"]
    ordered_times = sorted(time_dimension.items(), key=lambda item: item[1])
    values = dataset["value"]
    status = dataset.get("status", {})

    series = []
    for index, (period, _) in enumerate(ordered_times):
        value = values[index]
        if value is None or status.get(str(index)) == "..":
            continue
        series.append({"period": period, "value": float(value)})

    return series


def _jsonstat_pick_scalar(dataset: dict[str, object], **pick: str) -> float:
    """Læs én celle ud fra DST JSON-stat (alle dimensioner skal bindes; ContentsCode vælges automatisk)."""
    dim = dataset["dimension"]
    ids: list[str] = list(dim["id"])
    size: list[int] = list(dim["size"])
    vals = dataset["value"]
    idx_maps = {did: dim[did]["category"]["index"] for did in ids}
    filled: dict[str, str] = {}
    for did in ids:
        if did in pick:
            filled[did] = pick[did]
        elif did == "ContentsCode":
            filled[did] = next(iter(idx_maps[did].keys()))
        else:
            raise ValueError(f"Mangler dimension {did}")
    offset = 0
    stride = 1
    for i in range(len(ids) - 1, -1, -1):
        dname = ids[i]
        offset += idx_maps[dname][filled[dname]] * stride
        stride *= size[i]
    return float(vals[offset])


FU18_ALDER_CODES_ORDER: tuple[str, ...] = ("2001", "7010", "7020", "7030", "7040", "7050")


def fetch_housing_share_by_age_fu18_series() -> dict[str, object]:
    """FU18: bolig/energi (04) som andel af samlet forbrug (00); tidsserie for gennemsnitshusstand + seneste års aldersfordeling."""
    payload_ts = {
        "table": "FU18",
        "format": "JSONSTAT",
        "variables": [
            {"code": "KONSUMGRP", "values": ["04", "00"]},
            {"code": "ALDER", "values": ["2001"]},
            {"code": "PRISENHED", "values": ["AARPRIS"]},
            {"code": "Tid", "values": ["*"]},
        ],
    }
    raw_ts = fetch_json(DST_API_URL, payload_ts)
    ds_ts = raw_ts["dataset"]
    tid_index = ds_ts["dimension"]["Tid"]["category"]["index"]
    periods_sorted = sorted(tid_index.items(), key=lambda item: item[1])
    merged_series: list[dict[str, object]] = []
    for period, _ in periods_sorted:
        v04 = _jsonstat_pick_scalar(ds_ts, KONSUMGRP="04", ALDER="2001", PRISENHED="AARPRIS", Tid=period)
        v00 = _jsonstat_pick_scalar(ds_ts, KONSUMGRP="00", ALDER="2001", PRISENHED="AARPRIS", Tid=period)
        if v00 <= 0:
            continue
        merged_series.append({"period": period, "value": round(v04 / v00 * 100.0, 2)})
    if len(merged_series) < 2:
        raise ValueError("FU18: for f\u00e5 \u00e5r til boligandel-tidsserie")

    latest_period = str(merged_series[-1]["period"])

    payload_bd = {
        "table": "FU18",
        "format": "JSONSTAT",
        "variables": [
            {"code": "KONSUMGRP", "values": ["04", "00"]},
            {"code": "ALDER", "values": ["*"]},
            {"code": "PRISENHED", "values": ["AARPRIS"]},
            {"code": "Tid", "values": [latest_period]},
        ],
    }
    raw_bd = fetch_json(DST_API_URL, payload_bd)
    ds_bd = raw_bd["dataset"]
    alder_labels = ds_bd["dimension"]["ALDER"]["category"]["label"]

    age_breakdown: list[dict[str, object]] = []
    for code in FU18_ALDER_CODES_ORDER:
        if code not in alder_labels:
            continue
        v04 = _jsonstat_pick_scalar(ds_bd, KONSUMGRP="04", ALDER=code, PRISENHED="AARPRIS", Tid=latest_period)
        v00 = _jsonstat_pick_scalar(ds_bd, KONSUMGRP="00", ALDER=code, PRISENHED="AARPRIS", Tid=latest_period)
        if v00 <= 0:
            continue
        pct = round(v04 / v00 * 100.0, 2)
        label_txt = str(alder_labels[code]).strip()
        if code == "2001":
            label_txt = "Alle husstande (gennemsnit)"
        age_breakdown.append({"label": label_txt, "value": pct})

    updated_candidates = [
        str(ds_ts.get("updated") or ""),
        str(ds_bd.get("updated") or ""),
    ]
    updated_best = max((u for u in updated_candidates if u), default="")

    return {
        "updated": updated_best,
        "series": merged_series,
        "ageBreakdown": age_breakdown,
        "breakdownYear": latest_period,
        "sourceLabel": "Danmarks Statistik, FU18",
        "displayTable": "FU18",
    }


def fetch_dst_series(config: dict[str, object]) -> dict[str, object]:
    raw = fetch_json(
        DST_API_URL,
        {
            "table": config["table"],
            "format": "JSONSTAT",
            "variables": config["variables"],
        },
    )
    dataset = raw["dataset"]
    series = parse_jsonstat_series(dataset)
    if len(series) < 2:
        raise ValueError(f"Not enough data returned for table {config['table']}")

    divisor = float(config.get("valueDivisor", 1) or 1)
    if divisor != 1:
        for point in series:
            point["value"] = round(float(point["value"]) / divisor, 2)

    return {
        "updated": dataset.get("updated", ""),
        "series": series,
        "sourceLabel": config["sourceLabel"],
    }


def fetch_housing_burden_income_ratio_series() -> dict[str, object]:
    """Boligbyrde: FU12 COICOP 04 (kr/hush.) / FU19 disponibel indkomst M (kr/hush.), Forbrugsunders\u00f8gelsen."""
    payload_housing = {
        "table": "FU12",
        "format": "JSONSTAT",
        "variables": [
            {"code": "KONSUMGRP", "values": ["04"]},
            {"code": "PRISENHED", "values": ["AARPRIS"]},
            {"code": "Tid", "values": ["*"]},
        ],
    }
    payload_income = {
        "table": "FU19",
        "format": "JSONSTAT",
        "variables": [
            {"code": "INDKOMSTTYPE", "values": ["540"]},
            {"code": "Tid", "values": ["*"]},
        ],
    }

    raw_h = fetch_json(DST_API_URL, payload_housing)
    raw_i = fetch_json(DST_API_URL, payload_income)

    ds_h = raw_h["dataset"]
    ds_i = raw_i["dataset"]

    s_h = {p["period"]: p["value"] for p in parse_jsonstat_series(ds_h)}
    s_i = {p["period"]: p["value"] for p in parse_jsonstat_series(ds_i)}

    periods = sorted(
        set(s_h.keys()) & set(s_i.keys()),
        key=lambda y: int(y) if y.isdigit() else 0,
    )
    merged: list[dict[str, object]] = []
    for period in periods:
        housing_kr = float(s_h[period])
        disp_kr = float(s_i[period])
        if disp_kr <= 0:
            continue
        pct_val = round(housing_kr / disp_kr * 100.0, 2)
        merged.append({"period": period, "value": pct_val})

    if len(merged) < 2:
        raise ValueError("For f\u00e5 \u00e5r til boligbyrde-beregning")

    updated_candidates = [
        str(ds_h.get("updated") or ""),
        str(ds_i.get("updated") or ""),
    ]
    updated_best = max((u for u in updated_candidates if u), default="")

    return {
        "updated": updated_best,
        "series": merged,
        "sourceLabel": "Danmarks Statistik (FU12 + FU19)",
        "displayTable": "FU12 / FU19",
    }


def _yahoo_chart_json(ticker: str, range_param: str = "2y", interval: str = "1d") -> dict[str, object]:
    sym = quote(ticker, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={range_param}&interval={interval}"
    request = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Makroblik/1.0; +https://github.com)"},
        method="GET",
    )
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_yahoo_chart_closes(
    payload: dict[str, object], *, min_points: int = 5
) -> tuple[list[str], list[float], str]:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise ValueError("Ugyldigt Yahoo-svar")
    err = chart.get("error")
    if isinstance(err, dict):
        desc = err.get("description") or err.get("code") or "Yahoo Finance-fejl"
        raise ValueError(str(desc))
    result = chart.get("result")
    if not result:
        raise ValueError("Tomt resultat fra Yahoo Finance")

    block = result[0]
    timestamps = block.get("timestamp") or []
    indicators_block = block.get("indicators") or {}
    quotes = indicators_block.get("quote") or [{}]
    closes_raw = (quotes[0] or {}).get("close") if quotes else None
    if not isinstance(closes_raw, list) or not timestamps:
        raise ValueError("Manglende kursdata fra Yahoo Finance")

    meta = block.get("meta") or {}

    dates: list[str] = []
    closes: list[float] = []
    for ts, close in zip(timestamps, closes_raw):
        if ts is None or close is None:
            continue
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        dates.append(dt.strftime("%Y-%m-%d"))
        closes.append(float(close))

    if len(closes) < min_points:
        raise ValueError("For f\u00e5 datapunkter fra Yahoo Finance")

    updated_raw = meta.get("regularMarketTime")
    if isinstance(updated_raw, (int, float)):
        updated_at = datetime.fromtimestamp(int(updated_raw), tz=timezone.utc).strftime("%Y-%m-%d")
    else:
        updated_at = dates[-1] if dates else ""

    return dates, closes, updated_at


def fetch_omx_index_series() -> dict[str, object]:
    """Seneste ~1 års daglige lukkekurser for konfigureret Yahoo-indeks (standard OMX C25)."""
    ticker = STOCK_SENTIMENT_TICKER.strip() or "^OMXC25"
    degraded = False

    try:
        raw = _yahoo_chart_json(ticker, range_param="1y", interval="1d")
        dates, closes, updated_at = _parse_yahoo_chart_closes(raw, min_points=5)
        series = [{"period": d, "value": round(c, 2)} for d, c in zip(dates, closes)]
    except Exception:
        degraded = True
        series = [
            {"period": "2024-01-01", "value": 1700.0},
            {"period": "2024-01-02", "value": 1698.5},
        ]
        updated_at = ""

    sym_enc = quote(ticker, safe="")
    external_href = f"https://finance.yahoo.com/quote/{sym_enc}"
    link_label = f"Se {ticker} p\u00e5 Yahoo Finance"

    payload: dict[str, object] = {
        "updated": updated_at,
        "series": series,
        "sourceLabel": f"Yahoo Finance ({ticker})",
        "externalHref": external_href,
        "linkLabel": link_label,
        "displayTable": ticker,
    }
    if degraded:
        payload["sourceLabel"] = f"Yahoo Finance ({ticker}, midlertidig fallback)"
    return payload


def get_trend(current: float, previous: float, good_direction: str) -> dict[str, object]:
    if current == previous:
        return {"direction": "flat", "delta": 0, "label": "Stabil", "tone": "neutral"}

    moving_up = current > previous
    direction = "up" if moving_up else "down"
    delta = round(current - previous, 2)
    positive = direction == good_direction

    return {
        "direction": direction,
        "delta": delta,
        "label": "Stiger" if moving_up else "Falder",
        "tone": "positive" if positive else "warning",
    }


def quarter_label(period: str) -> str:
    year = period[:4]
    quarter = period[5:]
    return f"{quarter}. kvartal {year}"


def iso_date_label(period: str) -> str:
    """Formatér YYYY-MM-DD til dansk dato."""
    if len(period) >= 10 and period[4] == "-" and period[7] == "-":
        year = int(period[:4])
        month = int(period[5:7])
        day = int(period[8:10])
        month_names = [
            "januar",
            "februar",
            "marts",
            "april",
            "maj",
            "juni",
            "juli",
            "august",
            "september",
            "oktober",
            "november",
            "december",
        ]
        return f"{day}. {month_names[month - 1]} {year}"
    return period


def period_label_dk(period: str) -> str:
    """Kvartal/måned/år som i \u00f8vrige tekster (SILC/EJERFOF er \u00e5rlige: YYYY)."""
    if len(period) == 4 and period.isdigit():
        return period
    if "M" in period:
        return month_label(period)
    if "K" in period:
        return quarter_label(period)
    return period


def month_label(period: str) -> str:
    year = period[:4]
    month = int(period[5:7])
    month_names = [
        "januar",
        "februar",
        "marts",
        "april",
        "maj",
        "juni",
        "juli",
        "august",
        "september",
        "oktober",
        "november",
        "december",
    ]
    return f"{month_names[month - 1]} {year}"


def build_indicator(indicator_id: str, series_payload: dict[str, object]) -> dict[str, object]:
    config = SERIES_CONFIG[indicator_id]
    series = series_payload["series"]
    current_point = series[-1]
    previous_point = series[-2]
    history_cap = int(config.get("historyPoints", 12))
    history_cap = max(2, min(history_cap, len(series)))
    history = series[-history_cap:]

    href = series_payload.get("externalHref")
    if href is None:
        href = statbank_define_url(str(config["table"]))

    source_obj: dict[str, object] = {
        "table": series_payload.get("displayTable", config["table"]),
        "label": series_payload["sourceLabel"],
        "updated": series_payload["updated"],
        "href": href,
    }
    link_label = series_payload.get("linkLabel")
    if link_label:
        source_obj["linkLabel"] = link_label

    out: dict[str, object] = {
        "id": indicator_id,
        "label": config["label"],
        "unit": config["unit"],
        "current": current_point["value"],
        "previous": previous_point["value"],
        "goodDirection": config["goodDirection"],
        "importance": config["importance"],
        "explanation": config["explanation"],
        "chartMode": config.get("chartMode", "bar"),
        "scaleUnit": config.get("scaleUnit", config["unit"]),
        "includeZero": config.get("includeZero", False),
        "trend": get_trend(current_point["value"], previous_point["value"], config["goodDirection"]),
        "latestPeriod": current_point["period"],
        "previousPeriod": previous_point["period"],
        "history": history,
        "source": source_obj,
    }
    age_breakdown = series_payload.get("ageBreakdown")
    if isinstance(age_breakdown, list) and age_breakdown:
        out["ageBreakdown"] = age_breakdown
        by = series_payload.get("breakdownYear")
        if by:
            out["breakdownYear"] = by
    return out


def build_summary(indicators: list[dict[str, object]]) -> tuple[str, str, str, str]:
    def find_indicator(indicator_id: str) -> dict[str, object] | None:
        return next((item for item in indicators if item["id"] == indicator_id), None)

    inflation = find_indicator("inflation")
    unemployment = find_indicator("unemployment")
    gdp_growth = find_indicator("gdp-growth")
    consumer_confidence = find_indicator("consumer-confidence")
    retail_sales = find_indicator("retail-sales")
    industry_production = find_indicator("industry-production")
    housing_prices = find_indicator("housing-prices")
    housing_burden_income = find_indicator("housing-burden-income")
    housing_debt_families = find_indicator("housing-debt-families")
    realkredit_outstanding_hh = find_indicator("realkredit-outstanding-hh")
    interest_rate = find_indicator("interest-rate")
    business_confidence = find_indicator("business-confidence")
    export_growth = find_indicator("export-growth")
    private_consumption = find_indicator("private-consumption")
    fixed_investment = find_indicator("fixed-investment")
    import_growth = find_indicator("import-growth")
    government_consumption = find_indicator("government-consumption")
    stock_sentiment = find_indicator("stock-sentiment")
    new_car_household = find_indicator("new-car-registrations-household")
    new_car_business = find_indicator("new-car-registrations-business")

    outlook_score = 0
    for item in indicators:
        if item["trend"]["tone"] == "positive":
            outlook_score += 1
        elif item["trend"]["tone"] == "warning":
            outlook_score -= 1

    if outlook_score >= 2:
        outlook = "Bedre balance"
        outlook_text = (
            "Flere centrale n\u00f8gletal bev\u00e6ger sig i en retning, der ser mere balanceret ud for "
            "dansk \u00f8konomi."
        )
    elif outlook_score <= -2:
        outlook = "Afmatning"
        outlook_text = (
            "Flere af de vigtigste signaler peger mod en \u00f8konomi med mindre fart og st\u00f8rre "
            "s\u00e5rbarhed."
        )
    else:
        outlook = "Stabilisering"
        outlook_text = (
            "Dansk \u00f8konomi sender blandede signaler, men billedet ligner mest en rolig "
            "stabilisering frem for et brat skift."
        )

    summary_title = "Dansk \u00f8konomi i lavt tempo, men uden klare krisetegn"
    parts = []
    if inflation and unemployment and gdp_growth:
        parts.append(
            f"Inflationen ligger nu p\u00e5 {inflation['current']:.1f} pct. i {month_label(inflation['latestPeriod'])}, "
            f"AKU-ledigheden er {unemployment['current']:.1f} pct. i {quarter_label(unemployment['latestPeriod'])}, "
            f"og BNP voksede {gdp_growth['current']:.1f} pct. i {quarter_label(gdp_growth['latestPeriod'])}."
        )
    if consumer_confidence:
        parts.append(
            f"Forbrugertilliden ligger p\u00e5 {consumer_confidence['current']:.1f} i {month_label(consumer_confidence['latestPeriod'])}."
        )
    if new_car_household and new_car_business:
        parts.append(
            f"Nyregistrerede personbiler: {new_car_household['current']:.0f} med ejer i husholdninger og "
            f"{new_car_business['current']:.0f} med ejer i erhverv i "
            f"{month_label(new_car_household['latestPeriod'])}."
        )
    elif new_car_household:
        parts.append(
            f"Der blev nyregistreret {new_car_household['current']:.0f} personbiler i husholdningerne i "
            f"{month_label(new_car_household['latestPeriod'])}."
        )
    elif new_car_business:
        parts.append(
            f"Der blev nyregistreret {new_car_business['current']:.0f} personbiler i erhverv i "
            f"{month_label(new_car_business['latestPeriod'])}."
        )
    if retail_sales:
        parts.append(
            f"Detailsalget st\u00e5r p\u00e5 indeks {retail_sales['current']:.1f} i {month_label(retail_sales['latestPeriod'])}."
        )
    if industry_production:
        parts.append(
            f"Industrien ligger p\u00e5 indeks {industry_production['current']:.1f} i {month_label(industry_production['latestPeriod'])}."
        )
    if housing_prices:
        parts.append(
            f"Boligpriserne ændrer sig {housing_prices['current']:.1f} pct. i {quarter_label(housing_prices['latestPeriod'])}."
        )
    if housing_burden_income:
        parts.append(
            f"I Forbrugsunders\u00f8gelsen udgjorde bolig og energi (COICOP 04) ca. "
            f"{housing_burden_income['current']:.1f} pct. af den disponible indkomst i "
            f"{period_label_dk(str(housing_burden_income['latestPeriod']))}."
        )
    if housing_debt_families:
        parts.append(
            f"Familiernes samlede boligg\u00e6ld var {housing_debt_families['current']:.0f} mia. kr. i "
            f"{period_label_dk(str(housing_debt_families['latestPeriod']))}."
        )
    if realkredit_outstanding_hh:
        parts.append(
            f"Husholdningernes udest\u00e5ende realkredit var {realkredit_outstanding_hh['current']:.0f} mia. kr. "
            f"i {period_label_dk(str(realkredit_outstanding_hh['latestPeriod']))}."
        )
    if interest_rate:
        parts.append(
            f"Renten ligger p\u00e5 {interest_rate['current']:.1f} pct. i {month_label(interest_rate['latestPeriod'])}."
        )
    if business_confidence:
        parts.append(
            f"Erhvervstilliden ligger p\u00e5 {business_confidence['current']:.1f} i "
            f"{month_label(business_confidence['latestPeriod'])}."
        )
    if export_growth:
        parts.append(
            f"Eksporten voksede {export_growth['current']:.1f} pct. i "
            f"{quarter_label(export_growth['latestPeriod'])}."
        )
    if private_consumption:
        parts.append(
            f"Husholdningsforbruget steg {private_consumption['current']:.1f} pct. i "
            f"{quarter_label(private_consumption['latestPeriod'])}."
        )
    if fixed_investment:
        parts.append(
            f"De faste investeringer ændrede sig {fixed_investment['current']:.1f} pct. i "
            f"{quarter_label(fixed_investment['latestPeriod'])}."
        )
    if import_growth:
        parts.append(
            f"Importen voksede {import_growth['current']:.1f} pct. i "
            f"{quarter_label(import_growth['latestPeriod'])}."
        )
    if government_consumption:
        parts.append(
            f"Det offentlige forbrug steg {government_consumption['current']:.1f} pct. i "
            f"{quarter_label(government_consumption['latestPeriod'])}."
        )
    if stock_sentiment:
        parts.append(
            f"OMX C25 stod i {stock_sentiment['current']:.0f} "
            f"({iso_date_label(str(stock_sentiment['latestPeriod']))})."
        )

    summary_description = " ".join(parts) + " Det peger p\u00e5 en \u00f8konomi, der stadig bev\u00e6ger sig fremad, men i et mere forsigtigt tempo."

    return outlook, outlook_text, summary_title, summary_description


def _month_periods_ending(end_year: int, end_month: int, count: int) -> list[str]:
    out_rev: list[str] = []
    d = date(end_year, end_month, 1)
    for _ in range(count):
        out_rev.append(f"{d.year}M{d.month:02d}")
        if d.month == 1:
            d = date(d.year - 1, 12, 1)
        else:
            d = date(d.year, d.month - 1, 1)
    out_rev.reverse()
    return out_rev


_STUB_DISPLAY_BASE: dict[str, float] = {
    "inflation": 2.1,
    "unemployment": 5.5,
    "gdp-growth": 0.8,
    "consumer-confidence": -5.0,
    "new-car-registrations-household": 12000.0,
    "new-car-registrations-business": 8000.0,
    "private-consumption": 0.5,
    "retail-sales": 105.0,
    "government-consumption": 0.3,
    "business-confidence": 102.0,
    "industry-production": 108.0,
    "fixed-investment": -1.0,
    "export-growth": 1.2,
    "import-growth": 0.9,
    "housing-prices": 2.5,
    "housing-debt-families": 4100.0,
    "realkredit-outstanding-hh": 1680.0,
    "interest-rate": 3.4,
}


def _stub_series_payload(indicator_id: str) -> dict[str, object]:
    cfg = SERIES_CONFIG[indicator_id]
    src_label = str(cfg["sourceLabel"])
    disp = str(cfg.get("displayTable") or cfg["table"])

    if indicator_id == "stock-sentiment":
        series = []
        base_v = 1740.0
        d0 = date(2025, 4, 1)
        for i in range(45):
            d = d0 + timedelta(days=i)
            series.append({"period": d.isoformat(), "value": round(base_v + i * 0.4, 2)})
        sym = STOCK_SENTIMENT_TICKER.strip() or "^OMXC25"
        sym_enc = quote(sym, safe="")
        return {
            "updated": "2026-02-01",
            "series": series,
            "sourceLabel": src_label,
            "externalHref": f"https://finance.yahoo.com/quote/{sym_enc}",
            "linkLabel": f"Se {sym} p\u00e5 Yahoo Finance",
            "displayTable": sym,
        }

    if indicator_id == "housing-burden-income":
        years = list(range(2020, 2026))
        series = [
            {"period": str(y), "value": round(23.8 + (y - 2020) * 0.35, 2)} for y in years
        ]
        return {
            "updated": "2026-03-31T06:00:00Z",
            "series": series,
            "sourceLabel": src_label,
            "displayTable": "FU12 / FU19",
        }

    if indicator_id == "housing-share-age-fu18":
        years = list(range(2020, 2026))
        series = [{"period": str(y), "value": round(31.0 + (y - 2020) * 0.22, 2)} for y in years]
        return {
            "updated": "2026-02-26T07:00:00Z",
            "series": series,
            "ageBreakdown": [
                {"label": "Alle husstande (gennemsnit)", "value": 32.26},
                {"label": "Under 30 \u00e5r", "value": 33.63},
                {"label": "30-44 \u00e5r", "value": 30.88},
                {"label": "45-59 \u00e5r", "value": 28.95},
                {"label": "60-74 \u00e5r", "value": 32.89},
                {"label": "75 \u00e5r og derover", "value": 41.06},
            ],
            "breakdownYear": "2024",
            "sourceLabel": src_label,
            "displayTable": "FU18",
        }

    if indicator_id == "housing-debt-families":
        years = list(range(2020, 2026))
        series = [{"period": str(y), "value": round(3950.0 + (y - 2020) * 42.0, 2)} for y in years]
        return {
            "updated": "2026-02-15T00:00:00Z",
            "series": series,
            "sourceLabel": src_label,
            "displayTable": disp,
        }

    hp = max(2, min(int(cfg.get("historyPoints", 12)), 52))
    periods = _month_periods_ending(2026, 2, hp)
    base = _STUB_DISPLAY_BASE[indicator_id]
    series = []
    for i, p in enumerate(periods):
        drift = (i - (len(periods) - 1)) * 0.06
        series.append({"period": p, "value": round(base + drift, 2)})

    return {
        "updated": "2026-02-01T00:00:00Z",
        "series": series,
        "sourceLabel": src_label,
        "displayTable": disp,
    }


def build_fallback_payload() -> dict[str, object]:
    indicators: list[dict[str, object]] = []
    updated_dates: list[str] = []
    groups_payload: list[dict[str, object]] = []

    for group_id, group_title, indicator_ids in GROUP_DEFS:
        section_indicators: list[dict[str, object]] = []
        for indicator_id in indicator_ids:
            series_payload = _stub_series_payload(indicator_id)
            built = build_indicator(indicator_id, series_payload)
            section_indicators.append(built)
            indicators.append(built)
            updated_dates.append(str(series_payload.get("updated") or ""))
        groups_payload.append(
            {"id": group_id, "title": group_title, "indicators": section_indicators}
        )

    outlook, outlook_text, summary_title, summary_description = build_summary(indicators)
    clean_dates = [value[:10] for value in updated_dates if value]
    latest_update = max(clean_dates) if clean_dates else "2026-01-01"

    return {
        "updatedAt": latest_update,
        "summary": {"title": summary_title, "description": summary_description},
        "outlook": outlook,
        "outlookText": outlook_text,
        "live": False,
        "groups": groups_payload,
        "indicators": indicators,
    }


_FALLBACK_BUILT: dict[str, object] | None = None


def get_fallback_payload_copy() -> dict[str, object]:
    global _FALLBACK_BUILT
    if _FALLBACK_BUILT is None:
        _FALLBACK_BUILT = build_fallback_payload()
    return copy.deepcopy(_FALLBACK_BUILT)


macro_cache: dict[str, object] = {"expires_at": 0.0, "payload": get_fallback_payload_copy()}


def build_live_payload() -> dict[str, object]:
    indicators: list[dict[str, object]] = []
    updated_dates: list[str] = []
    groups_payload: list[dict[str, object]] = []

    for group_id, group_title, indicator_ids in GROUP_DEFS:
        section_indicators: list[dict[str, object]] = []
        for indicator_id in indicator_ids:
            if indicator_id == "stock-sentiment":
                series_payload = fetch_omx_index_series()
            elif indicator_id == "housing-burden-income":
                series_payload = fetch_housing_burden_income_ratio_series()
            elif indicator_id == "housing-share-age-fu18":
                series_payload = fetch_housing_share_by_age_fu18_series()
            else:
                series_payload = fetch_dst_series(SERIES_CONFIG[indicator_id])
            built = build_indicator(indicator_id, series_payload)
            section_indicators.append(built)
            indicators.append(built)
            updated_dates.append(series_payload["updated"])
        groups_payload.append(
            {
                "id": group_id,
                "title": group_title,
                "indicators": section_indicators,
            }
        )

    outlook, outlook_text, summary_title, summary_description = build_summary(indicators)
    clean_dates = [value[:10] for value in updated_dates if value]
    latest_update = max(clean_dates) if clean_dates else datetime.utcnow().strftime("%Y-%m-%d")

    return {
        "updatedAt": latest_update,
        "summary": {"title": summary_title, "description": summary_description},
        "outlook": outlook,
        "outlookText": outlook_text,
        "live": True,
        "groups": groups_payload,
        "indicators": indicators,
    }


def augment_payload_with_stock_sentiment(payload: dict[str, object]) -> dict[str, object]:
    """Sørg for at OMX C25 er med — også når DST-kørslen fejler og vi bruger fallback."""
    indicators = list(payload.get("indicators") or [])
    if any(item.get("id") == "stock-sentiment" for item in indicators):
        return payload

    try:
        series_payload = fetch_omx_index_series()
        stock = build_indicator("stock-sentiment", series_payload)
    except Exception:
        return payload

    merged_indicators = indicators + [stock]
    out: dict[str, object] = {**payload, "indicators": merged_indicators}

    groups_in = payload.get("groups")
    if not groups_in:
        dst_only = [item for item in indicators if item.get("id") != "stock-sentiment"]
        out["groups"] = [
            {"id": "fallback-core", "title": None, "indicators": dst_only},
            {"id": "markets", "title": "Markeder", "indicators": [stock]},
        ]
        return out

    if any(g.get("id") == "markets" for g in groups_in):
        return out

    out["groups"] = list(groups_in) + [
        {"id": "markets", "title": "Markeder", "indicators": [stock]},
    ]
    return out


def get_macro_payload() -> dict[str, object]:
    now = time.time()
    cached = macro_cache.get("payload")
    cached_live = cached.get("live") if isinstance(cached, dict) else None
    cache_ttl_ok = macro_cache["expires_at"] > now and cached and isinstance(cached, dict) and "live" in cached
    live_payload_ok = (
        cached_live is True
        and len(cached.get("indicators", [])) == len(INDICATOR_IDS)
        and len(cached.get("groups", [])) == len(GROUP_DEFS)
    )
    fallback_payload_ok = cached_live is False
    if cache_ttl_ok and (live_payload_ok or fallback_payload_ok):
        return cached

    try:
        payload = build_live_payload()
    except Exception:
        payload = get_fallback_payload_copy()

    payload = augment_payload_with_stock_sentiment(payload)

    macro_cache["payload"] = payload
    macro_cache["expires_at"] = now + CACHE_TTL_SECONDS
    return payload


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/macro":
            body = json.dumps(get_macro_payload(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/":
            file_path = PUBLIC_DIR / "index.html"
        else:
            file_path = (PUBLIC_DIR / parsed.path.lstrip("/")).resolve()
            if PUBLIC_DIR.resolve() not in file_path.parents and file_path != PUBLIC_DIR.resolve():
                self.send_error(404)
                return

        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return

        content = file_path.read_bytes()
        suffix = file_path.suffix
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml; charset=utf-8",
        }.get(suffix, "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Makrotool running on http://{HOST}:{PORT}")
    server.serve_forever()
