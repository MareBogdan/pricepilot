/* Dashboard charts (Chart.js 4). Colors come from CSS variables so light/dark follow the page.
 * Fixed entity colors: a shop keeps its color on every chart. Our own price is neutral ink.
 * Status colors are reserved for APPROVE / FLAG / REJECT. Marks are thin, bars are rounded at the
 * data end, grids are hairlines, and every chart has a table view under it. */
(function () {
  "use strict";
  var PP = (window.PP = {});
  var SHOP_VAR = { animax_ro: "--s1", pentruanimale_ro: "--s2", petmax_ro: "--s3" };

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  PP.css = css;
  PP.shopColor = function (shop) { return css(SHOP_VAR[shop] || "--muted"); };
  PP.shopName = function (shop) { return shop.replace(/_ro$/, ".ro"); };
  PP.ready = function () { return typeof Chart !== "undefined"; };

  function setDefaults() {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css("--muted");
    Chart.defaults.animation = false; // data is static; no motion needed
  }

  function grid() { return { color: css("--line"), lineWidth: 1, drawTicks: false }; }

  /* Writes a value at the tip of each bar (or centered inside a stacked segment when it fits). */
  var valueLabels = {
    id: "valueLabels",
    afterDatasetsDraw: function (chart, _args, opts) {
      if (!opts || !opts.format) { return; }
      var ctx = chart.ctx;
      ctx.save();
      ctx.font = "600 12px " + Chart.defaults.font.family;
      ctx.textBaseline = "middle";
      chart.data.datasets.forEach(function (ds, di) {
        var meta = chart.getDatasetMeta(di);
        if (meta.hidden) { return; }
        meta.data.forEach(function (bar, i) {
          var v = ds.data[i];
          if (v === null || v === undefined || (opts.skipZero && Number(v) === 0)) { return; }
          var text = opts.format(v, ds, i);
          var w = ctx.measureText(text).width;
          if (opts.inside) {
            var segment = Math.abs(bar.x - bar.base);
            if (segment < w + 12) { return; } // never clip: legend + tooltip + table carry it
            ctx.fillStyle = (opts.insideColors && opts.insideColors[di]) || "#0b0b0b";
            ctx.textAlign = "center";
            ctx.fillText(text, (bar.x + bar.base) / 2, bar.y);
          } else {
            ctx.fillStyle = css("--text");
            ctx.textAlign = "left";
            ctx.fillText(text, bar.x + 8, bar.y);
          }
        });
      });
      ctx.restore();
    }
  };

  function tooltipBase() {
    return {
      backgroundColor: css("--surface"), titleColor: css("--text"), bodyColor: css("--text"),
      borderColor: css("--line"), borderWidth: 1, padding: 10, boxPadding: 4, cornerRadius: 8
    };
  }

  /* Our price vs each matched competitor price (and the guard-approved recommendation). */
  PP.priceBars = function (canvasId, items) {
    var el = document.getElementById(canvasId);
    if (!el || !PP.ready() || !items.length) { return; }
    setDefaults();
    el.parentNode.style.height = 64 + items.length * 46 + "px";
    var colors = items.map(function (it) {
      if (it.kind === "ours") { return css("--ink"); }
      if (it.kind === "rec") { return css("--st-good"); }
      return PP.shopColor(it.shop);
    });
    new Chart(el, {
      type: "bar",
      plugins: [valueLabels],
      data: {
        labels: items.map(function (it) { return it.label; }),
        datasets: [{
          data: items.map(function (it) { return Number(it.price); }),
          backgroundColor: colors, borderRadius: { topRight: 4, bottomRight: 4 },
          borderSkipped: "start", maxBarThickness: 24, categoryPercentage: 0.8
        }]
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        layout: { padding: { right: 8 } },
        scales: {
          x: { beginAtZero: true, grace: "24%", grid: grid(), border: { display: false },
               ticks: { color: css("--muted") } },
          y: { grid: { display: false }, border: { color: css("--line") },
               ticks: { color: css("--text"), font: { size: 13 } } }
        },
        plugins: {
          legend: { display: false },
          valueLabels: { format: function (v) { return v.toFixed(2); } },
          tooltip: Object.assign(tooltipBase(), { callbacks: {
            label: function (c) { return c.parsed.x.toFixed(2) + " RON"; } } })
        }
      }
    });
  };

  var STATUS = [
    { key: "approve", label: "APPROVE", variable: "--st-good", text: "#0b0b0b" },
    { key: "flag", label: "FLAG", variable: "--st-warn", text: "#0b0b0b" },
    { key: "reject", label: "REJECT", variable: "--st-crit", text: "#ffffff" }
  ];

  /* Guard verdicts per input group (stacked). rows: [{label, approve, flag, reject}] */
  PP.verdictMix = function (canvasId, rows) {
    var el = document.getElementById(canvasId);
    if (!el || !PP.ready() || !rows.length) { return; }
    setDefaults();
    el.parentNode.style.height = 96 + rows.length * 44 + "px";
    var surface = css("--surface");
    new Chart(el, {
      type: "bar",
      plugins: [valueLabels],
      data: {
        labels: rows.map(function (r) { return r.label; }),
        datasets: STATUS.map(function (s) {
          return {
            label: s.label, data: rows.map(function (r) { return r[s.key]; }),
            backgroundColor: css(s.variable), borderColor: surface, borderWidth: 2,
            maxBarThickness: 28
          };
        })
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        scales: {
          x: { stacked: true, beginAtZero: true, grid: grid(), border: { display: false },
               ticks: { color: css("--muted"), precision: 0 } },
          y: { stacked: true, grid: { display: false }, border: { color: css("--line") },
               ticks: { color: css("--text") } }
        },
        plugins: {
          legend: { position: "top", align: "start",
                    labels: { color: css("--text"), usePointStyle: true, boxWidth: 8, padding: 14 } },
          valueLabels: { inside: true, skipZero: true,
                         insideColors: STATUS.map(function (s) { return s.text; }),
                         format: function (v) { return String(v); } },
          tooltip: Object.assign(tooltipBase(), { callbacks: {
            label: function (c) { return c.dataset.label + ": " + c.parsed.x; } } })
        }
      }
    });
  };

  /* Average margin per category against the policy floor. rows: [{label, avg, floor}] */
  PP.marginBars = function (canvasId, rows) {
    var el = document.getElementById(canvasId);
    if (!el || !PP.ready() || !rows.length) { return; }
    setDefaults();
    el.parentNode.style.height = 96 + rows.length * 52 + "px";
    new Chart(el, {
      type: "bar",
      plugins: [valueLabels],
      data: {
        labels: rows.map(function (r) { return r.label; }),
        datasets: [
          { label: "Average margin", data: rows.map(function (r) { return Number(r.avg); }),
            backgroundColor: css("--ink"), borderRadius: { topRight: 4, bottomRight: 4 },
            borderSkipped: "start", maxBarThickness: 16 },
          { label: "Policy margin floor", data: rows.map(function (r) { return Number(r.floor); }),
            backgroundColor: css("--muted"), borderRadius: { topRight: 4, bottomRight: 4 },
            borderSkipped: "start", maxBarThickness: 16 }
        ]
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        layout: { padding: { right: 8 } },
        scales: {
          x: { beginAtZero: true, grace: "12%", grid: grid(), border: { display: false },
               ticks: { color: css("--muted"), callback: function (v) { return v + "%"; } } },
          y: { grid: { display: false }, border: { color: css("--line") },
               ticks: { color: css("--text") } }
        },
        plugins: {
          legend: { position: "top", align: "start",
                    labels: { color: css("--text"), usePointStyle: true, boxWidth: 8, padding: 14 } },
          valueLabels: { format: function (v) { return v.toFixed(1) + "%"; } },
          tooltip: Object.assign(tooltipBase(), { callbacks: {
            label: function (c) { return c.dataset.label + ": " + c.parsed.x.toFixed(1) + "%"; } } })
        }
      }
    });
  };

  /* Competitor prices (real, solid, stepped) and our price (simulated, dashed). */
  PP.history = function (canvasId, h, msgEl, btn) {
    var el = document.getElementById(canvasId);
    if (!el || !PP.ready()) { return; }
    setDefaults();
    function ts(day) { return Date.parse(day + "T00:00:00Z"); }
    function fmt(ms) { return new Date(ms).toISOString().slice(0, 10); }
    var datasets = h.competitors_real.map(function (s) {
      var color = PP.shopColor(s.shop);
      return {
        label: PP.shopName(s.shop) + " (real)",
        data: s.points.map(function (p) { return { x: ts(p[0]), y: Number(p[1]) }; }),
        borderColor: color, backgroundColor: color, borderWidth: 2, pointRadius: 3,
        pointBorderColor: css("--surface"), pointBorderWidth: 2, stepped: "before"
      };
    });
    if (h.our_price_synthetic.length) {
      datasets.push({
        label: "Our price (simulated)",
        data: h.our_price_synthetic.map(function (p) { return { x: ts(p.day), y: Number(p.price) }; }),
        borderColor: css("--ink"), backgroundColor: css("--ink"), borderDash: [6, 4],
        borderWidth: 2, pointRadius: 0
      });
    }
    var firstReal = Infinity;
    h.competitors_real.forEach(function (s) {
      s.points.forEach(function (p) { firstReal = Math.min(firstReal, ts(p[0])); });
    });
    var lastX = Math.max.apply(null, datasets.map(function (d) {
      return d.data.length ? d.data[d.data.length - 1].x : 0;
    }));
    var windowMin = isFinite(firstReal) ? firstReal - 3 * 86400000 : undefined;
    var chart = new Chart(el, {
      type: "line", data: { datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "nearest", axis: "x", intersect: false },
        scales: {
          x: { type: "linear", min: windowMin, max: lastX, grid: grid(), border: { display: false },
               ticks: { color: css("--muted"), maxTicksLimit: 7, callback: function (v) { return fmt(v); } } },
          y: { grid: grid(), border: { display: false }, ticks: { color: css("--muted") },
               title: { display: true, text: "RON", color: css("--muted") } }
        },
        plugins: {
          legend: { position: "top", align: "start",
                    labels: { color: css("--text"), usePointStyle: true, boxWidth: 8, padding: 14 } },
          tooltip: Object.assign(tooltipBase(), { callbacks: {
            title: function (items) { return fmt(items[0].parsed.x); },
            label: function (c) { return c.dataset.label + ": " + c.parsed.y.toFixed(2) + " RON"; } } })
        }
      }
    });
    if (windowMin !== undefined && btn) {
      var full = false;
      btn.hidden = false;
      btn.addEventListener("click", function () {
        full = !full;
        chart.options.scales.x.min = full ? undefined : windowMin;
        chart.update();
        btn.textContent = full ? "Show collected period only" : "Show full simulated history";
      });
    }
    if (!h.competitors_real.length && msgEl) {
      msgEl.textContent = "No matched competitor, so only our simulated price is shown.";
    }
  };
})();
