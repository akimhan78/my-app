(() => {
  "use strict";

  const state = { data: null, districtMap: new Map(), dongMap: new Map() };
  const format = (value, digits = 2) => Number.isFinite(value)
    ? new Intl.NumberFormat("ko-KR", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
    : "자료 없음";
  const formatCount = (value) => new Intl.NumberFormat("ko-KR").format(value || 0);
  const pct = (value) => Number.isFinite(value) ? `${format(value)}%` : "자료 없음";
  const $ = (selector) => document.querySelector(selector);

  async function loadData() {
    const response = await fetch("/data/dashboard.json.gz");
    if (!response.ok) throw new Error(`분석 자료 요청에 실패했습니다 (${response.status}).`);
    if (!("DecompressionStream" in window)) throw new Error("이 브라우저는 압축된 분석 자료를 열 수 없습니다. 최신 Chrome, Edge 또는 Firefox를 이용해 주세요.");
    const stream = response.body.pipeThrough(new DecompressionStream("gzip"));
    const payload = await new Response(stream).json();
    state.data = payload;
    payload.districts.forEach((district) => state.districtMap.set(district.name, district));
    payload.dongs.forEach((dong) => state.dongMap.set(`${dong.district}|${dong.name}`, dong));
  }

  const chartLayout = (title = "") => ({
    title: title ? { text: title, x: 0.02, xanchor: "left", font: { size: 14, color: "#263a57" } } : undefined,
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "DM Sans, Noto Sans KR, sans-serif", color: "#66748a", size: 10 },
    margin: { l: 55, r: 18, t: 28, b: 48 },
    xaxis: { type: "category", tickangle: -35, showgrid: false, linecolor: "#e2e7ef", tickfont: { size: 9 }, automargin: true },
    yaxis: { title: { text: "만원/㎡", font: { size: 9 } }, gridcolor: "#edf0f5", zeroline: false, tickfont: { size: 9 }, automargin: true },
    hoverlabel: { bgcolor: "#172b4d", font: { color: "white", size: 11 } },
    legend: { orientation: "h", y: 1.12, x: 0, font: { size: 10 } },
  });
  const plotConfig = { responsive: true, displayModeBar: false };

  function getDistrict(name) { return state.districtMap.get(name); }
  function getDong(district, name) { return state.dongMap.get(`${district}|${name}`); }
  function months() { return state.data.months; }
  function priceLine(series, label, color, sparse = false) {
    return {
      x: series.map((item) => item.month),
      y: series.map((item) => sparse && item.count < 5 ? null : item.price),
      customdata: series.map((item) => [item.count]),
      type: "scatter", mode: "lines+markers", name: label,
      connectgaps: false,
      line: { color, width: 2.5 }, marker: { size: 4 },
      hovertemplate: "%{x}<br>㎡당 전세가격 중앙값: %{y:,.2f}만원/㎡<br>거래: %{customdata[0]:,}건<extra>%{fullData.name}</extra>",
    };
  }

  function change(from, to) {
    if (!Number.isFinite(from) || !Number.isFinite(to) || from === 0) return NaN;
    return (to / from - 1) * 100;
  }

  function monthlyStats(series) {
    const valid = series.filter((row) => row.count > 0 && Number.isFinite(row.price));
    if (!valid.length) return { recent: NaN, oneYear: NaN, fiveYear: NaN, volatility: NaN, count: 0 };
    const last = valid[valid.length - 1];
    const previousYear = series.find((row) => row.month === shiftMonth(last.month, -12));
    const first = valid[0];
    const returns = [];
    for (let i = 1; i < series.length; i += 1) {
      const previous = series[i - 1];
      const current = series[i];
      if (previous.count > 0 && current.count > 0 && Number.isFinite(previous.price) && Number.isFinite(current.price) && previous.price !== 0) {
        returns.push(current.price / previous.price - 1);
      }
    }
    const average = returns.length ? returns.reduce((sum, value) => sum + value, 0) / returns.length : NaN;
    const variance = returns.length > 1
      ? returns.reduce((sum, value) => sum + (value - average) ** 2, 0) / (returns.length - 1)
      : NaN;
    return {
      recent: last.price,
      oneYear: previousYear?.count > 0 ? change(previousYear.price, last.price) : NaN,
      fiveYear: change(first.price, last.price),
      volatility: Number.isFinite(variance) ? Math.sqrt(variance) * 100 : NaN,
      count: valid.reduce((sum, row) => sum + row.count, 0),
      lastMonth: last.month,
    };
  }

  function shiftMonth(month, delta) {
    const [year, monthNumber] = month.split("-").map(Number);
    const date = new Date(Date.UTC(year, monthNumber - 1 + delta, 1));
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
  }

  function statCards(container, entries) {
    const root = $(container);
    root.replaceChildren();
    entries.forEach(([label, value, unit = "", hint = ""]) => {
      const card = document.createElement("div");
      card.className = "metric-card";
      const title = document.createElement("div");
      title.className = "metric-label";
      title.textContent = label;
      const number = document.createElement("div");
      number.className = "metric-value";
      number.append(document.createTextNode(value));
      if (unit) {
        const suffix = document.createElement("span");
        suffix.className = "metric-unit";
        suffix.textContent = unit;
        number.append(suffix);
      }
      card.append(title, number);
      if (hint) {
        const detail = document.createElement("div");
        detail.className = "metric-hint";
        detail.textContent = hint;
        card.append(detail);
      }
      root.append(card);
    });
  }

  function fillSelect(select, values, selected = "") {
    const element = $(select);
    const previous = selected || element.value;
    element.replaceChildren();
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      element.append(option);
    });
    if (values.includes(previous)) element.value = previous;
  }

  function renderMap() {
    const districts = state.data.districts;
    const z = districts.map((item) => item.recentYearMedian);
    const recentYearStart = shiftMonth(state.data.months[state.data.months.length - 1], -11);
    const trace = {
      type: "choropleth", geojson: state.data.geojson,
      featureidkey: "properties.SIGUNGU_NM",
      locations: districts.map((item) => item.name), z,
      text: districts.map((item) => item.name),
      customdata: districts.map((item) => {
        const sum = item.monthly.reduce((total, month) => total + (month.month >= recentYearStart ? month.count : 0), 0);
        return [item.recentYearMedian, sum];
      }),
      colorscale: [[0, "#edf3ff"], [0.35, "#b7ccf6"], [0.7, "#6f96e9"], [1, "#2854ad"]],
      zmin: Math.min(...z.filter(Number.isFinite)), zmax: Math.max(...z.filter(Number.isFinite)),
      marker: { line: { color: "#fff", width: 1.5 } },
      colorbar: { title: { text: "만원/㎡", side: "right", font: { size: 10 } }, thickness: 10, len: 0.75, tickfont: { size: 9 } },
      hovertemplate: "%{location}<br>최근 1년 중앙값: %{customdata[0]:,.2f}만원/㎡<br>거래: %{customdata[1]:,}건<extra></extra>",
    };
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)", margin: { l: 0, r: 0, t: 5, b: 0 },
      geo: { fitbounds: "locations", visible: false, bgcolor: "rgba(0,0,0,0)", projection: { type: "mercator" }, showframe: false },
    };
    Plotly.newPlot("district-map", [trace], layout, plotConfig).then((chart) => {
      chart.on("plotly_click", (event) => {
        const selected = event.points?.[0]?.location;
        if (selected && getDistrict(selected)) {
          $("#trend-district").value = selected;
          updateTrendDongOptions();
          renderTrend();
        }
      });
    });
  }

  function renderTrend() {
    const districtName = $("#trend-district").value;
    const dongName = $("#trend-dong").value;
    const district = getDistrict(districtName);
    const dong = getDong(districtName, dongName);
    if (!district || !dong) return;
    const reliableDongSeries = dong.monthly.map((row) => row.count < 5 ? { ...row, price: null, count: 0 } : row);
    const validDongMonths = reliableDongSeries.filter((row) => row.count > 0 && Number.isFinite(row.price));
    const stableStats = monthlyStats(reliableDongSeries);
    statCards("#trend-metrics", [
      ["최근 가격 중앙값", format(stableStats.recent), "만원/㎡", stableStats.lastMonth || "월 5건 이상 기준"],
      ["최근 1년 변화율", pct(stableStats.oneYear), "", "최근 유효 월 기준"],
      ["최근 5년 변화율", pct(stableStats.fiveYear), "", "유효 월 첫 값과 비교"],
      ["월별 가격 변동성", pct(stableStats.volatility), "", "월 변화율 표준편차"],
      ["전체 거래 건수", formatCount(dong.monthly.reduce((sum, row) => sum + row.count, 0)), "건", "월 5건 미만 포함"],
    ]);
    const traces = [
      priceLine(dong.monthly, `${dongName} (월 5건 이상)`, "#346be8", true),
      priceLine(district.monthly, `${districtName} 전체`, "#e09a47"),
    ];
    const seoul = months().map((month, index) => {
      const parts = state.data.districts.map((item) => item.monthly[index]).filter((row) => row.count > 0);
      // 서울 전체 중앙값은 이 데이터셋의 개별 거래 중앙값을 집계한 값으로 제공됩니다.
      return { month, price: state.data.seoulMonthly[index].price, count: parts.reduce((sum, row) => sum + row.count, 0) };
    });
    traces.push(priceLine(seoul, "서울 전체", "#3da889"));
    Plotly.react("trend-chart", traces, chartLayout(), plotConfig);
    $("#trend-chart-title").textContent = `${districtName} ${dongName} · 자치구 · 서울 전체`;

    const candidates = validDongMonths;
    const peak = candidates.reduce((best, row) => !best || row.price > best.price ? row : best, null);
    const lowest = candidates.reduce((best, row) => !best || row.price < best.price ? row : best, null);
    $("#peak-note").textContent = peak && lowest
      ? `월 5건 이상인 달 가운데 중앙값은 ${peak.month}에 가장 높고 (${format(peak.price)}만원/㎡), ${lowest.month}에 가장 낮았습니다 (${format(lowest.price)}만원/㎡).`
      : "월 거래 5건 이상인 달이 없어 최고·최저 시점을 계산할 수 없습니다.";
  }

  function updateTrendDongOptions() {
    const district = $("#trend-district").value;
    const names = state.data.dongs.filter((dong) => dong.district === district).map((dong) => dong.name);
    fillSelect("#trend-dong", [...new Set(names)].sort());
  }

  const metricDefinitions = [
    ["recent", "최근 가격 수준", "만원/㎡"],
    ["oneYear", "최근 1년 변화율", "%"],
    ["fiveYear", "최근 5년 변화율", "%"],
    ["volatility", "월별 가격 변동성", "%"],
    ["count", "거래 건수", "건"],
  ];

  function renderComparison() {
    const nameA = $("#compare-a").value;
    const nameB = $("#compare-b").value;
    const districtA = getDistrict(nameA);
    const districtB = getDistrict(nameB);
    if (!districtA || !districtB) return;
    const a = monthlyStats(districtA.monthly);
    const b = monthlyStats(districtB.monthly);
    statCards("#compare-metrics", metricDefinitions.map(([key, label, unit]) => [
      label,
      key === "count" ? `${formatCount(a[key])} · ${formatCount(b[key])}` : `${key === "recent" ? format(a[key]) : pct(a[key])} · ${key === "recent" ? format(b[key]) : pct(b[key])}`,
      key === "count" ? "A · B 건" : unit,
      `${nameA} · ${nameB}`,
    ]));
    Plotly.react("compare-line", [
      priceLine(districtA.monthly, nameA, "#346be8"),
      priceLine(districtB.monthly, nameB, "#e09a47"),
    ], chartLayout(), plotConfig);

    const bodyRows = metricDefinitions.map(([key, label, unit]) => [label, key === "count" ? formatCount(a[key]) : (key === "recent" ? format(a[key]) : pct(a[key])), key === "count" ? formatCount(b[key]) : (key === "recent" ? format(b[key]) : pct(b[key])), unit]);
    setTable("#compare-table", ["지표", nameA, nameB, "단위"], bodyRows);
    const cards = $("#compare-bars");
    cards.replaceChildren();
    metricDefinitions.forEach(([key, label, unit], index) => {
      const card = document.createElement("article");
      card.className = "card small-chart-card";
      const title = document.createElement("p");
      title.className = "small-chart-title";
      title.textContent = label;
      const chart = document.createElement("div");
      chart.className = "small-chart";
      chart.id = `compare-bar-${index}`;
      card.append(title, chart);
      cards.append(card);
      const valueA = a[key];
      const valueB = b[key];
      Plotly.newPlot(chart, [{
        type: "bar", x: [nameA, nameB], y: [valueA, valueB],
        marker: { color: ["#4779df", "#e2a258"], borderRadius: 4 },
        text: key === "count" ? [formatCount(valueA), formatCount(valueB)] : [format(valueA), format(valueB)],
        textposition: "outside", cliponaxis: false,
        hovertemplate: `%{x}<br>${label}: %{y:,.2f} ${unit}<extra></extra>`,
      }], {
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 8, r: 8, t: 12, b: 30 }, showlegend: false,
        font: { family: "DM Sans, Noto Sans KR, sans-serif", size: 9, color: "#738096" },
        xaxis: { showgrid: false, linecolor: "#e7ebf2" },
        yaxis: { showgrid: true, gridcolor: "#eef1f6", zeroline: false, title: { text: unit, font: { size: 8 } } },
      }, plotConfig);
    });
  }

  function setTable(selector, headers, rows) {
    const table = $(selector);
    table.replaceChildren();
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    headers.forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headerRow.append(th);
    });
    thead.append(headerRow);
    const tbody = document.createElement("tbody");
    rows.forEach((values) => {
      const tr = document.createElement("tr");
      values.forEach((value, index) => {
        const td = document.createElement("td");
        td.textContent = String(value ?? "자료 없음");
        if (index === 0 && typeof value === "number") {
          const rank = document.createElement("span");
          rank.className = "rank-pill";
          rank.textContent = String(value);
          td.replaceChildren(rank);
        }
        tr.append(td);
      });
      tbody.append(tr);
    });
    table.append(thead, tbody);
  }

  function districtFeatures() {
    return state.data.districts.map((district) => {
      const summary = monthlyStats(district.monthly);
      return {
        name: district.name,
        recentYearMedian: district.recentYearMedian,
        fiveYearChange: summary.fiveYear,
        volatility: summary.volatility,
        monthly: district.monthly,
        count: summary.count,
      };
    });
  }

  function renderSimilar() {
    const selected = $("#similar-district").value;
    const features = districtFeatures();
    const target = features.find((item) => item.name === selected);
    if (!target) return;
    const keys = ["recentYearMedian", "fiveYearChange", "volatility"];
    const means = keys.map((key) => features.reduce((sum, item) => sum + item[key], 0) / features.length);
    const deviations = keys.map((key, i) => Math.sqrt(features.reduce((sum, item) => sum + (item[key] - means[i]) ** 2, 0) / features.length) || 1);
    const distances = features.filter((item) => item.name !== selected).map((item) => {
      const distance = Math.sqrt(keys.reduce((sum, key, i) => sum + (((item[key] - means[i]) / deviations[i]) - ((target[key] - means[i]) / deviations[i])) ** 2, 0));
      return { ...item, distance };
    }).sort((a, b) => a.distance - b.distance).slice(0, 3);
    statCards("#similar-reference-metrics", [
      ["최근 1년 ㎡당 중앙값", format(target.recentYearMedian), "만원/㎡"],
      ["최근 5년 가격 변화율", pct(target.fiveYearChange), ""],
      ["월별 가격 변동성", pct(target.volatility), ""],
      ["최근 가격 수준", format(monthlyStats(target.monthly).recent), "만원/㎡"],
      ["전체 거래 건수", formatCount(target.count), "건"],
    ]);
    const recommendations = distances.map((item, index) => [index + 1, item.name, format(item.distance, 4), format(item.recentYearMedian), pct(item.fiveYearChange), pct(item.volatility)]);
    setTable("#similar-table", ["순위", "자치구명", "거리값", "최근 1년 중앙값 (만원/㎡)", "5년 변화율", "월별 변동성"], recommendations);
    const allRows = [[selected, target.recentYearMedian, target.fiveYearChange, target.volatility], ...distances.map((item) => [item.name, item.recentYearMedian, item.fiveYearChange, item.volatility])];
    setTable("#similar-feature-table", ["자치구", "최근 1년 ㎡당 중앙값 (만원/㎡)", "최근 5년 변화율 (%)", "월별 변동성 (%)"], allRows.map(([name, price, changeValue, volatility]) => [name, format(price), pct(changeValue), pct(volatility)]));
    const trendTraces = [target, ...distances].map((item, index) => priceLine(item.monthly, item.name, ["#244d91", "#4c86e8", "#e2a258", "#54a68e"][index]));
    Plotly.react("similar-line", trendTraces, chartLayout(), plotConfig);
  }

  function setupTabs() {
    document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((tab) => {
        const active = tab === button;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.hidden = panel.id !== `panel-${button.dataset.tab}`;
        panel.classList.toggle("active", !panel.hidden);
      });
      window.dispatchEvent(new Event("resize"));
    }));
  }

  async function start() {
    try {
      await loadData();
      if (!window.Plotly) throw new Error("그래프 라이브러리를 불러오지 못했습니다. 네트워크 연결을 확인해 주세요.");
      $("#date-range").textContent = `${state.data.startDate} — ${state.data.latestDate} · 최근 5년 데이터`;
      const names = state.data.districts.map((district) => district.name).sort();
      fillSelect("#trend-district", names, "마포구");
      updateTrendDongOptions();
      fillSelect("#compare-a", names, "마포구");
      fillSelect("#compare-b", names.filter((name) => name !== $("#compare-a").value), "강남구");
      fillSelect("#similar-district", names, "마포구");
      $("#trend-district").addEventListener("change", () => { updateTrendDongOptions(); renderTrend(); });
      $("#trend-dong").addEventListener("change", renderTrend);
      $("#compare-a").addEventListener("change", () => {
        const options = names.filter((name) => name !== $("#compare-a").value);
        fillSelect("#compare-b", options);
        renderComparison();
      });
      $("#compare-b").addEventListener("change", renderComparison);
      $("#similar-district").addEventListener("change", renderSimilar);
      setupTabs();
      $("#loading").classList.add("hidden");
      $("#dashboard").classList.remove("hidden");
      renderMap();
      renderTrend();
      renderComparison();
      renderSimilar();
    } catch (error) {
      $("#loading").classList.add("hidden");
      $("#app-error").textContent = `대시보드를 불러오지 못했습니다. ${error.message}`;
      $("#app-error").classList.remove("hidden");
    }
  }

  start();
})();
