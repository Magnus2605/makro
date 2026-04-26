from __future__ import annotations

import json
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PORT = 3000
PUBLIC_DIR = Path(__file__).parent / "public"
DST_API_URL = "https://api.statbank.dk/v1/data"
CACHE_TTL_SECONDS = 60 * 60 * 6


FALLBACK_PAYLOAD = {
    "updatedAt": "2026-04-26",
    "summary": {
        "title": "Dansk \u00f8konomi viser blandede, men rolige signaler",
        "description": (
            "Inflationen er kommet ned fra de h\u00f8jeste niveauer, arbejdsmarkedet er stadig "
            "forholdsvis robust, og BNP vokser svagt. Det peger mere mod lav fart end mod et "
            "pludseligt h\u00e5rdt tilbageslag."
        ),
    },
    "outlook": "Stabilisering",
    "outlookText": (
        "De fleste n\u00f8gletal bev\u00e6ger sig i en retning, der tyder p\u00e5 en mere balanceret dansk "
        "\u00f8konomi, men tempoet er ikke specielt h\u00f8jt."
    ),
    "indicators": [
        {
            "id": "inflation",
            "label": "Inflation",
            "unit": "%",
            "current": 1.2,
            "previous": 0.7,
            "goodDirection": "down",
            "importance": "H\u00f8j",
            "explanation": (
                "Inflation viser hvor hurtigt priserne stiger. Lavere inflation g\u00f8r det lettere "
                "for husholdninger at f\u00f8lge med."
            ),
            "trend": {
                "direction": "up",
                "delta": 0.5,
                "label": "Stiger",
                "tone": "warning",
            },
            "source": {"table": "PRIS01", "label": "Danmarks Statistik"},
        },
        {
            "id": "unemployment",
            "label": "AKU-ledighed",
            "unit": "%",
            "current": 6.6,
            "previous": 6.5,
            "goodDirection": "down",
            "importance": "H\u00f8j",
            "explanation": (
                "Ledigheden viser hvor stor en del af arbejdsstyrken der st\u00e5r uden job, men "
                "aktivt s\u00f8ger arbejde."
            ),
            "trend": {
                "direction": "up",
                "delta": 0.1,
                "label": "Stiger",
                "tone": "warning",
            },
            "source": {"table": "AKU101K", "label": "Danmarks Statistik"},
        },
        {
            "id": "gdp-growth",
            "label": "BNP-v\u00e6kst",
            "unit": "%",
            "current": 0.2,
            "previous": 2.3,
            "goodDirection": "up",
            "importance": "H\u00f8j",
            "explanation": (
                "BNP-v\u00e6kst fort\u00e6ller om den samlede aktivitet i \u00f8konomien. N\u00e5r v\u00e6ksten "
                "bliver lavere, er det ofte et tegn p\u00e5, at tempoet i \u00f8konomien falder."
            ),
            "trend": {
                "direction": "down",
                "delta": -2.1,
                "label": "Falder",
                "tone": "warning",
            },
            "source": {"table": "NKN1", "label": "Danmarks Statistik"},
        },
    ],
}


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
        "importance": "Mellem",
        "explanation": (
            "Forbrugertilliden viser, hvordan danskerne ser på økonomien lige nu og lidt frem. "
            "Når den stiger, peger det ofte på mere optimisme og mindre forsigtighed."
        ),
        "sourceLabel": "Danmarks Statistik, FORV1",
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
}


macro_cache: dict[str, object] = {
    "expires_at": 0.0,
    "payload": FALLBACK_PAYLOAD,
}


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

    return {
        "updated": dataset.get("updated", ""),
        "series": series,
        "sourceLabel": config["sourceLabel"],
    }


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
    history = series[-12:]

    return {
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
        "trend": get_trend(current_point["value"], previous_point["value"], config["goodDirection"]),
        "latestPeriod": current_point["period"],
        "previousPeriod": previous_point["period"],
        "history": history,
        "source": {
            "table": config["table"],
            "label": series_payload["sourceLabel"],
            "updated": series_payload["updated"],
        },
    }


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
    interest_rate = find_indicator("interest-rate")

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
    if interest_rate:
        parts.append(
            f"Renten ligger p\u00e5 {interest_rate['current']:.1f} pct. i {month_label(interest_rate['latestPeriod'])}."
        )

    summary_description = " ".join(parts) + " Det peger p\u00e5 en \u00f8konomi, der stadig bev\u00e6ger sig fremad, men i et mere forsigtigt tempo."

    return outlook, outlook_text, summary_title, summary_description


def build_live_payload() -> dict[str, object]:
    indicators = []
    updated_dates = []

    for indicator_id in (
        "inflation",
        "unemployment",
        "gdp-growth",
        "consumer-confidence",
        "retail-sales",
        "industry-production",
        "housing-prices",
        "interest-rate",
    ):
        series_payload = fetch_dst_series(SERIES_CONFIG[indicator_id])
        indicators.append(build_indicator(indicator_id, series_payload))
        updated_dates.append(series_payload["updated"])

    outlook, outlook_text, summary_title, summary_description = build_summary(indicators)
    clean_dates = [value[:10] for value in updated_dates if value]
    latest_update = max(clean_dates) if clean_dates else datetime.utcnow().strftime("%Y-%m-%d")

    return {
        "updatedAt": latest_update,
        "summary": {"title": summary_title, "description": summary_description},
        "outlook": outlook,
        "outlookText": outlook_text,
        "indicators": indicators,
    }


def get_macro_payload() -> dict[str, object]:
    now = time.time()
    if macro_cache["expires_at"] > now:
        return macro_cache["payload"]

    try:
        payload = build_live_payload()
    except Exception:
        payload = FALLBACK_PAYLOAD

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
        }.get(suffix, "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Makrotool running on http://localhost:{PORT}")
    server.serve_forever()
