function formatWithUnit(value, unit) {
  if (!unit) {
    return String(value);
  }

  return unit === "%" ? `${value}%` : `${value} ${unit}`;
}

function formatValue(value, unit) {
  return formatWithUnit(value, unit);
}

function formatCompactValue(value) {
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString("da-DK", { maximumFractionDigits: 1 });
  }

  return value.toLocaleString("da-DK", {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 1,
    maximumFractionDigits: 1
  });
}

function formatChartValue(value, unit) {
  return formatWithUnit(formatCompactValue(value), unit);
}

function formatPeriod(period) {
  if (!period) {
    return "";
  }

  if (period.includes("M")) {
    const year = period.slice(0, 4);
    const month = Number(period.slice(5, 7));
    const months = [
      "jan",
      "feb",
      "mar",
      "apr",
      "maj",
      "jun",
      "jul",
      "aug",
      "sep",
      "okt",
      "nov",
      "dec"
    ];
    return `${months[month - 1]} ${year}`;
  }

  if (period.includes("K")) {
    const year = period.slice(0, 4);
    const quarter = period.slice(5);
    return `${quarter}. kvt. ${year}`;
  }

  return period;
}

function trendCopy(trend, previousPeriod) {
  if (trend.direction === "flat") {
    return `U\u00e6ndret siden ${formatPeriod(previousPeriod)}`;
  }

  const deltaValue = Math.abs(trend.delta);
  return `${trend.label} med ${deltaValue} siden ${formatPeriod(previousPeriod)}`;
}

function buildHistoryScale(history, options = {}) {
  const mode = options.mode || "bar";
  const includeZero = Boolean(options.includeZero);
  const values = history.map((item) => item.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const hasNegative = min < 0;
  const padding = Math.max((max - min) * 0.15, Math.abs(max) * 0.1, 0.5);
  const linePadding = Math.max((max - min) * 0.15, Math.abs(max) * 0.08, Math.abs(min) * 0.08, 0.5);
  let scaleMin;
  let scaleMax;

  if (mode === "line") {
    const bottomPadding = Math.max(linePadding, Math.abs(min) * 0.18, 1.5);
    const topPadding = Math.max(linePadding * 0.6, Math.abs(max) * 0.06, 0.5);
    scaleMin = min - bottomPadding;
    scaleMax = max + topPadding;
    if (includeZero) {
      scaleMin = Math.min(scaleMin, 0);
      scaleMax = Math.max(scaleMax, 0);
    }
  } else {
    scaleMin = hasNegative ? Math.min(min - padding, 0) : 0;
    scaleMax = Math.max(max + padding, 0);
  }

  const range = scaleMax - scaleMin || 1;
  const zeroFromTop = ((scaleMax - 0) / range) * 100;

  return {
    min: scaleMin,
    max: scaleMax,
    zeroFromTop,
    hasNegative,
    showZeroLine: mode === "line" ? (includeZero || (min < 0 && max > 0)) : hasNegative,
    bars: history.map((item, index) => {
      if (mode === "line") {
        const x = history.length > 1 ? (index / (history.length - 1)) * 100 : 50;
        const prevX = index > 0 ? (history.length > 1 ? ((index - 1) / (history.length - 1)) * 100 : 50) : 0;
        const nextX = index < history.length - 1 ? (history.length > 1 ? ((index + 1) / (history.length - 1)) * 100 : 50) : 100;
        const left = index === 0 ? 0 : (prevX + x) / 2;
        const right = index === history.length - 1 ? 100 : (x + nextX) / 2;
        const width = Math.max(right - left, 4);
        const dotX = width > 0 ? ((x - left) / width) * 100 : 50;

        return {
          ...item,
          x,
          left,
          width,
          dotX,
          y: ((scaleMax - item.value) / range) * 100,
          isNegative: item.value < 0
        };
      }

      const positiveHeight = Math.max(((Math.max(item.value, 0) - 0) / range) * 100, 4);
      const negativeHeight = Math.max(((0 - Math.min(item.value, 0)) / range) * 100, 4);
      const zeroTop = Math.min(Math.max(zeroFromTop, 0), 100);

      return {
        ...item,
        top: item.value < 0
          ? `${zeroTop}%`
          : `${Math.max(zeroTop - positiveHeight, 0)}%`,
        height: `${item.value < 0 ? negativeHeight : positiveHeight}%`,
        isNegative: item.value < 0
      };
    })
  };
}

async function loadMacroData() {
  const response = await fetch("/api/macro");
  if (!response.ok) {
    throw new Error("Kunne ikke hente makrodata");
  }

  return response.json();
}

function buildLinePath(points) {
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
}

function renderIndicator(indicator) {
  const template = document.getElementById("indicator-template");
  const node = template.content.firstElementChild.cloneNode(true);
  const chartMode = indicator.chartMode || "bar";
  const scaleUnit = indicator.scaleUnit ?? indicator.unit;
  const history = buildHistoryScale(indicator.history || [], {
    mode: chartMode,
    includeZero: indicator.id === "consumer-confidence"
  });

  node.querySelector(".card-label").textContent = indicator.label;
  node.querySelector(".card-value").textContent = formatValue(indicator.current, indicator.unit);
  node.querySelector(".card-explanation").textContent = indicator.explanation;
  node.querySelector(".importance").textContent = `${indicator.importance} betydning`;
  node.querySelector(".delta").textContent = trendCopy(indicator.trend, indicator.previousPeriod);

  const pill = node.querySelector(".trend-pill");
  pill.textContent = indicator.trend.label;
  pill.dataset.tone = indicator.trend.tone;

  const scaleTop = node.querySelector(".scale-top");
  const scaleMid = node.querySelector(".scale-mid");
  const scaleBottom = node.querySelector(".scale-bottom");
  const historyStart = node.querySelector(".history-start");
  const historyEnd = node.querySelector(".history-end");
  const historyPlot = node.querySelector(".history-plot");

  const midpointValue = history.showZeroLine
    ? (history.max <= 0 ? history.min / 2 : history.min >= 0 ? history.max / 2 : 0)
    : (history.max + history.min) / 2;

  if (chartMode === "line") {
    scaleTop.textContent = history.showZeroLine && history.max <= 0
      ? formatChartValue(0, scaleUnit)
      : formatChartValue(history.max, scaleUnit);
    scaleMid.textContent = formatChartValue(midpointValue, scaleUnit);
    scaleBottom.textContent = formatChartValue(history.min, scaleUnit);
  } else {
    scaleTop.textContent = formatChartValue(history.max, scaleUnit);
    scaleMid.textContent = history.showZeroLine ? formatChartValue(0, scaleUnit) : "";
    scaleBottom.textContent = history.showZeroLine ? formatChartValue(history.min, scaleUnit) : formatChartValue(0, scaleUnit);
  }
  historyStart.textContent = formatPeriod(history.bars[0]?.period);
  historyEnd.textContent = formatPeriod(history.bars[history.bars.length - 1]?.period);

  historyPlot.innerHTML = "";
  historyPlot.style.setProperty("--zero-line", `${Math.min(Math.max(history.zeroFromTop, 0), 100)}%`);
  historyPlot.classList.toggle("has-negative", history.showZeroLine);
  historyPlot.classList.toggle("is-line", chartMode === "line");
  historyPlot.dataset.tone = indicator.trend.tone;

  if (chartMode === "line") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.classList.add("history-line-svg");

    const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const points = history.bars;
    const baselineY = history.showZeroLine ? Math.min(Math.max(history.zeroFromTop, 0), 100) : 100;
    const linePath = buildLinePath(points);
    const areaPath = points.length
      ? `${linePath} L ${points[points.length - 1].x.toFixed(2)} ${baselineY.toFixed(2)} L ${points[0].x.toFixed(2)} ${baselineY.toFixed(2)} Z`
      : "";

    area.setAttribute("d", areaPath);
    area.classList.add("history-area");
    line.setAttribute("d", linePath);
    line.classList.add("history-line");

    svg.appendChild(area);
    svg.appendChild(line);
    historyPlot.appendChild(svg);

    points.forEach((item) => {
      const point = document.createElement("button");
      point.type = "button";
      point.className = `history-point${item.isNegative ? " is-negative" : ""}`;
      point.title = `${formatPeriod(item.period)}: ${formatWithUnit(formatCompactValue(item.value), indicator.unit)}`;
      point.setAttribute("aria-label", `${formatPeriod(item.period)} ${formatWithUnit(formatCompactValue(item.value), indicator.unit)}`);
      point.style.left = `${item.left}%`;
      point.style.width = `${item.width}%`;
      point.style.top = "0";
      point.style.height = "100%";
      point.style.setProperty("--dot-x", `${item.dotX}%`);
      point.style.setProperty("--point-y", `${item.y}%`);

      const tooltip = document.createElement("span");
      tooltip.className = "bar-tooltip";
      tooltip.textContent = formatWithUnit(formatCompactValue(item.value), indicator.unit);

      point.appendChild(tooltip);
      historyPlot.appendChild(point);
    });
  } else {
    history.bars.forEach((item) => {
      const bar = document.createElement("button");
      bar.type = "button";
      bar.className = `history-bar${item.isNegative ? " is-negative" : ""}`;
      bar.title = `${formatPeriod(item.period)}: ${formatWithUnit(formatCompactValue(item.value), indicator.unit)}`;
      bar.setAttribute("aria-label", `${formatPeriod(item.period)} ${formatWithUnit(formatCompactValue(item.value), indicator.unit)}`);

      const tooltip = document.createElement("span");
      tooltip.className = "bar-tooltip";
      tooltip.textContent = formatWithUnit(formatCompactValue(item.value), indicator.unit);

      const fill = document.createElement("span");
      fill.className = "bar-fill";
      fill.style.top = item.top;
      fill.style.height = item.height;

      bar.appendChild(fill);
      bar.appendChild(tooltip);
      historyPlot.appendChild(bar);
    });
  }

  return node;
}

function renderDashboard(data) {
  document.getElementById("outlook-title").textContent = data.outlook;
  document.getElementById("outlook-text").textContent = data.outlookText;
  document.getElementById("updated-at").textContent = data.updatedAt;
  document.getElementById("summary-title").textContent = data.summary.title;
  document.getElementById("summary-description").textContent = data.summary.description;

  const grid = document.getElementById("indicator-grid");
  grid.innerHTML = "";
  data.indicators.forEach((indicator) => {
    grid.appendChild(renderIndicator(indicator));
  });
}

function renderError(message) {
  const grid = document.getElementById("indicator-grid");
  grid.innerHTML = `<article class="indicator-card"><h3>Fejl</h3><p class="card-explanation">${message}</p></article>`;
}

loadMacroData().then(renderDashboard).catch((error) => {
  renderError(error.message);
});
