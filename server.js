const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = process.env.PORT || 3000;
const PUBLIC_DIR = path.join(__dirname, "public");

const macroData = {
  updatedAt: "2026-04-26",
  summary: {
    title: "\u00d8konomien k\u00f8ler lidt af, men er ikke p\u00e5 vej i frit fald",
    description:
      "Inflationen er kommet mere under kontrol, renterne er stadig forholdsvis h\u00f8je, og arbejdsmarkedet viser de f\u00f8rste tegn p\u00e5 at blive mindre stramt. Det peger mod langsommere v\u00e6kst, men ikke n\u00f8dvendigvis recession her og nu."
  },
  indicators: [
    {
      id: "inflation",
      label: "Inflation",
      unit: "%",
      current: 2.4,
      previous: 3.1,
      goodDirection: "down",
      importance: "H\u00f8j",
      explanation:
        "N\u00e5r inflationen falder, bliver prisstigningerne mindre voldsomme. Det er ofte en lettelse for husholdninger, men det kan ogs\u00e5 v\u00e6re tegn p\u00e5 lavere eftersp\u00f8rgsel."
    },
    {
      id: "interest-rate",
      label: "Styringsrente",
      unit: "%",
      current: 3.75,
      previous: 4,
      goodDirection: "down",
      importance: "H\u00f8j",
      explanation:
        "Lavere renter kan g\u00f8re l\u00e5n billigere og give mere aktivitet i \u00f8konomien. Men centralbanker s\u00e6nker ofte f\u00f8rst renterne, n\u00e5r de mener, at inflationen er under bedre kontrol."
    },
    {
      id: "unemployment",
      label: "Arbejdsl\u00f8shed",
      unit: "%",
      current: 4.2,
      previous: 3.9,
      goodDirection: "down",
      importance: "H\u00f8j",
      explanation:
        "N\u00e5r arbejdsl\u00f8sheden stiger, er det typisk et tegn p\u00e5, at virksomheder bliver mere forsigtige. Sm\u00e5 stigninger kan v\u00e6re normale, men st\u00f8rre hop er ofte et advarselssignal."
    },
    {
      id: "gdp-growth",
      label: "BNP-v\u00e6kst",
      unit: "%",
      current: 1.3,
      previous: 1.8,
      goodDirection: "up",
      importance: "Mellem",
      explanation:
        "BNP-v\u00e6ksten siger noget om, hvor hurtigt \u00f8konomien vokser. N\u00e5r v\u00e6ksten aftager, peger det p\u00e5 lavere tempo i forbrug, investeringer og erhvervsaktivitet."
    },
    {
      id: "consumer-confidence",
      label: "Forbrugertillid",
      unit: "",
      current: 96,
      previous: 92,
      goodDirection: "up",
      importance: "Mellem",
      explanation:
        "Forbrugertillid handler om, hvor trygge folk f\u00f8ler sig ved deres \u00f8konomi. N\u00e5r tilliden stiger, er folk ofte mere villige til at bruge penge."
    }
  ]
};

function getTrend(current, previous, goodDirection) {
  if (current === previous) {
    return {
      direction: "flat",
      delta: 0,
      label: "Stabil",
      tone: "neutral"
    };
  }

  const movingUp = current > previous;
  const direction = movingUp ? "up" : "down";
  const delta = Number((current - previous).toFixed(2));
  const positive = direction === goodDirection;

  return {
    direction,
    delta,
    label: movingUp ? "Stiger" : "Falder",
    tone: positive ? "positive" : "warning"
  };
}

function buildApiPayload() {
  const indicators = macroData.indicators.map((indicator) => ({
    ...indicator,
    trend: getTrend(indicator.current, indicator.previous, indicator.goodDirection)
  }));

  const warningCount = indicators.filter((item) => item.trend.tone === "warning").length;
  const positiveCount = indicators.filter((item) => item.trend.tone === "positive").length;

  let outlook = "Blandet";
  let outlookText =
    "Nogle dele af \u00f8konomien ser bedre ud, mens andre peger mod lavere fart. Det er et klassisk billede p\u00e5 en \u00f8konomi i overgang.";

  if (warningCount >= 3) {
    outlook = "Afmatning";
    outlookText =
      "Flere n\u00f8gletal peger mod en \u00f8konomi, der taber fart. Det betyder ikke automatisk krise, men risikoen for svagere v\u00e6kst er stigende.";
  } else if (positiveCount >= 3) {
    outlook = "Stabilisering";
    outlookText =
      "De fleste n\u00f8gletal bev\u00e6ger sig i en retning, der g\u00f8r \u00f8konomien mere balanceret. Det ligner mere en opbremsning end et h\u00e5rdt tilbageslag.";
  }

  return {
    ...macroData,
    outlook,
    outlookText,
    indicators
  };
}

function sendJson(res, data) {
  res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(data));
}

function sendFile(res, filePath) {
  fs.readFile(filePath, (err, content) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    const extension = path.extname(filePath);
    const contentTypes = {
      ".html": "text/html; charset=utf-8",
      ".css": "text/css; charset=utf-8",
      ".js": "application/javascript; charset=utf-8"
    };

    res.writeHead(200, {
      "Content-Type": contentTypes[extension] || "application/octet-stream"
    });
    res.end(content);
  });
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === "/api/macro") {
    sendJson(res, buildApiPayload());
    return;
  }

  const requestedPath = url.pathname === "/" ? "/index.html" : url.pathname;
  const safePath = path.normalize(requestedPath).replace(/^(\.\.[/\\])+/, "");
  const filePath = path.join(PUBLIC_DIR, safePath);

  sendFile(res, filePath);
});

server.listen(PORT, () => {
  console.log(`Makrotool running on http://localhost:${PORT}`);
});
