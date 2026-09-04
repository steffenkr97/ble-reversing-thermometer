/* ThermoBeacon Dashboard — lokal, kein Build. */
(function () {
  "use strict";

  var SOURCE_LABELS = {
    adv: "Live-CSV (ADV)",
    history: "History-CSV",
    adv_capture: "Capture-ADV",
    history_capture: "History-Capture (07)",
  };

  var SOURCE_HINTS = {
    adv: "Sammelzeit UTC aus collect.py. Eine Zeile = ein ADV-Sample.",
    history:
      "GATT-History-Dump (dump_history.py). Zeit = Hypothese 10 min, sonst Index 0 = älteste.",
    adv_capture: "HCI-Beleg ADV_IND, nur Allowlist. Kein Live-Collector.",
    history_capture:
      "HCI-Beleg GATT 07. Index 0 = älteste. Capture-Zeit ist Dump-Zeit, nicht Gerätezeit.",
  };

  var state = {
    overview: null,
    roomId: null,
    source: null,
    samples: [],
    hover: -1,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function fmtNum(value, digits) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    return Number(value).toLocaleString("de-DE", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    var normalized = iso.replace(/Z$/, "+00:00");
    var d = new Date(normalized);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("de-DE", { timeZone: "UTC", hour12: false }) + " UTC";
  }

  function roomOf(overview, id) {
    var rooms = (overview && overview.rooms) || [];
    for (var i = 0; i < rooms.length; i++) {
      if (rooms[i].id === id) return rooms[i];
    }
    return rooms[0] || null;
  }

  function pickDefaultSource(room) {
    if (!room) return "adv";
    var counts = room.counts || {};
    if (counts.adv) return "adv";
    if (counts.history) return "history";
    if (counts.history_capture) return "history_capture";
    if (counts.adv_capture) return "adv_capture";
    return "adv";
  }

  function sourcesFor(room) {
    var order = ["adv", "history", "adv_capture", "history_capture"];
    var out = [];
    for (var i = 0; i < order.length; i++) {
      var key = order[i];
      var n = room && room.counts ? room.counts[key] || 0 : 0;
      out.push({ key: key, count: n });
    }
    return out;
  }

  function api(path) {
    return fetch(path, { cache: "no-store" }).then(function (res) {
      if (!res.ok) {
        return res.json().then(function (body) {
          throw new Error(body.error || res.statusText);
        });
      }
      return res.json();
    });
  }

  function renderRooms() {
    var host = $("rooms");
    host.innerHTML = "";
    var rooms = (state.overview && state.overview.rooms) || [];
    if (!rooms.length) {
      host.innerHTML =
        '<article class="room"><p class="name">Keine Räume</p><p class="status">rooms.json ist leer.</p></article>';
      return;
    }
    rooms.forEach(function (room) {
      var btn = document.createElement("button");
      btn.className = "room" + (room.id === state.roomId ? " active" : "");
      btn.type = "button";
      var latest = room.latest;
      var temp = latest ? fmtNum(latest.temp_c, 3) : "—";
      var hum = latest ? fmtNum(latest.humidity_rh, 2) : "—";
      var liveN = room.counts.adv || 0;
      var status =
        liveN > 0
          ? liveN + " Live-Samples"
          : "Noch keine Live-CSV — Capture-Beleg verfügbar";
      btn.innerHTML =
        '<p class="name"></p><p class="mac"></p>' +
        '<div class="readout">' +
        '<div class="val temp">' +
        temp +
        "<small>°C</small></div>" +
        '<div class="val hum">' +
        hum +
        "<small>%rF</small></div></div>" +
        '<p class="status"></p>';
      btn.querySelector(".name").textContent = room.name;
      btn.querySelector(".mac").textContent = room.mac;
      btn.querySelector(".status").textContent = status;
      btn.addEventListener("click", function () {
        state.roomId = room.id;
        state.source = pickDefaultSource(room);
        renderRooms();
        renderTabs();
        loadSamples();
      });
      host.appendChild(btn);
    });
  }

  function renderMeta() {
    var ov = state.overview;
    if (!ov) return;
    var live = ov.live_csv_count || 0;
    $("top-meta").innerHTML =
      live +
      " Live-CSV · " +
      (ov.sample_count || 0) +
      " Punkte gesamt<br>Büro-Allowlist, Encoding int16le / 16";
  }

  function renderTabs() {
    var room = roomOf(state.overview, state.roomId);
    var host = $("source-tabs");
    host.innerHTML = "";
    sourcesFor(room).forEach(function (item) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = item.key === state.source ? "active" : "";
      btn.textContent = SOURCE_LABELS[item.key] + " (" + item.count + ")";
      btn.disabled = item.count === 0;
      btn.addEventListener("click", function () {
        state.source = item.key;
        renderTabs();
        loadSamples();
      });
      host.appendChild(btn);
    });
  }

  function renderKpis(summary) {
    var host = $("kpis");
    var items = [
      ["Aktuell °C", fmtNum(summary.temp_c, 3)],
      ["Aktuell %rF", fmtNum(summary.humidity_rh, 2)],
      ["Spanne °C", fmtNum(summary.temp_min, 2) + " – " + fmtNum(summary.temp_max, 2)],
      ["Punkte", String(summary.count || 0)],
    ];
    host.innerHTML = items
      .map(function (item) {
        return (
          '<div class="kpi"><div class="label">' +
          item[0] +
          '</div><div class="num">' +
          item[1] +
          "</div></div>"
        );
      })
      .join("");
  }

  function historyUsesTime(samples) {
    if (state.source !== "history") return false;
    for (var i = 0; i < samples.length; i++) {
      if (samples[i].timestamp) return true;
    }
    return false;
  }

  function xValue(sample, i) {
    if (state.source === "history_capture") {
      return sample.index == null ? i : sample.index;
    }
    if (state.source === "history" && !historyUsesTime(state.samples)) {
      return sample.index == null ? i : sample.index;
    }
    if (sample.timestamp) {
      var t = Date.parse(sample.timestamp.replace(/Z$/, "+00:00"));
      if (!Number.isNaN(t)) return t;
    }
    if (state.source === "history" && sample.index != null) return sample.index;
    return i;
  }

  function xLabel(sample, i) {
    if (state.source === "history_capture") {
      return "Index " + (sample.index == null ? i : sample.index);
    }
    if (state.source === "history") {
      if (sample.timestamp) {
        var idx = sample.index == null ? "" : " · Index " + sample.index;
        return fmtTime(sample.timestamp) + idx;
      }
      return "Index " + (sample.index == null ? i : sample.index);
    }
    return fmtTime(sample.timestamp);
  }

  function drawChart() {
    var canvas = $("chart");
    var samples = state.samples;
    var ctx = canvas.getContext("2d");
    var dpr = window.devicePixelRatio || 1;
    var cssW = canvas.clientWidth || 1200;
    var cssH = 380;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    var pad = { l: 52, r: 52, t: 18, b: 36 };
    var w = cssW - pad.l - pad.r;
    var h = cssH - pad.t - pad.b;
    ctx.fillStyle = "#faf6ee";
    ctx.fillRect(0, 0, cssW, cssH);

    if (!samples.length) return;

    var xs = samples.map(xValue);
    var temps = samples.map(function (s) {
      return s.temp_c;
    });
    var hums = samples.map(function (s) {
      return s.humidity_rh;
    });
    var minX = Math.min.apply(null, xs);
    var maxX = Math.max.apply(null, xs);
    if (minX === maxX) {
      minX -= 1;
      maxX += 1;
    }
    var tMin = Math.min.apply(null, temps);
    var tMax = Math.max.apply(null, temps);
    var hMin = Math.min.apply(null, hums);
    var hMax = Math.max.apply(null, hums);
    var tPad = Math.max(0.4, (tMax - tMin) * 0.12);
    var hPad = Math.max(1.5, (hMax - hMin) * 0.12);
    tMin -= tPad;
    tMax += tPad;
    hMin -= hPad;
    hMax += hPad;

    function xPos(v) {
      return pad.l + ((v - minX) / (maxX - minX)) * w;
    }
    function yTemp(v) {
      return pad.t + (1 - (v - tMin) / (tMax - tMin)) * h;
    }
    function yHum(v) {
      return pad.t + (1 - (v - hMin) / (hMax - hMin)) * h;
    }

    ctx.strokeStyle = "#d4ccba";
    ctx.lineWidth = 1;
    ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
    ctx.fillStyle = "#6d675c";
    var ticks = 4;
    for (var g = 0; g <= ticks; g++) {
      var gy = pad.t + (h * g) / ticks;
      ctx.beginPath();
      ctx.moveTo(pad.l, gy);
      ctx.lineTo(pad.l + w, gy);
      ctx.stroke();
      var tv = tMax - ((tMax - tMin) * g) / ticks;
      var hv = hMax - ((hMax - hMin) * g) / ticks;
      ctx.textAlign = "right";
      ctx.fillStyle = "#c45c26";
      ctx.fillText(fmtNum(tv, 1), pad.l - 8, gy + 3);
      ctx.textAlign = "left";
      ctx.fillStyle = "#1d6b6b";
      ctx.fillText(fmtNum(hv, 0), pad.l + w + 8, gy + 3);
    }

    function line(values, yFn, color) {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      for (var i = 0; i < samples.length; i++) {
        var x = xPos(xs[i]);
        var y = yFn(values[i]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    line(temps, yTemp, "#c45c26");
    line(hums, yHum, "#1d6b6b");

    if (state.hover >= 0 && state.hover < samples.length) {
      var hx = xPos(xs[state.hover]);
      ctx.beginPath();
      ctx.strokeStyle = "#1c1914";
      ctx.setLineDash([3, 3]);
      ctx.moveTo(hx, pad.t);
      ctx.lineTo(hx, pad.t + h);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#c45c26";
      ctx.beginPath();
      ctx.arc(hx, yTemp(temps[state.hover]), 3.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#1d6b6b";
      ctx.beginPath();
      ctx.arc(hx, yHum(hums[state.hover]), 3.5, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.fillStyle = "#6d675c";
    ctx.textAlign = "left";
    ctx.fillText(xLabel(samples[0], 0), pad.l, cssH - 12);
    ctx.textAlign = "right";
    ctx.fillText(xLabel(samples[samples.length - 1], samples.length - 1), pad.l + w, cssH - 12);
  }

  function bindChart() {
    var canvas = $("chart");
    var tooltip = $("tooltip");
    canvas.onmousemove = function (ev) {
      var samples = state.samples;
      if (!samples.length) return;
      var rect = canvas.getBoundingClientRect();
      var x = ev.clientX - rect.left;
      var padL = 52;
      var padR = 52;
      var w = rect.width - padL - padR;
      var rel = (x - padL) / w;
      if (rel < 0 || rel > 1) {
        state.hover = -1;
        tooltip.hidden = true;
        drawChart();
        return;
      }
      var xs = samples.map(xValue);
      var minX = Math.min.apply(null, xs);
      var maxX = Math.max.apply(null, xs);
      var target = minX + rel * (maxX - minX);
      var best = 0;
      var bestD = Infinity;
      for (var i = 0; i < xs.length; i++) {
        var d = Math.abs(xs[i] - target);
        if (d < bestD) {
          bestD = d;
          best = i;
        }
      }
      state.hover = best;
      var s = samples[best];
      tooltip.hidden = false;
      tooltip.style.left = Math.min(rect.width - 170, Math.max(8, x + 12)) + "px";
      tooltip.style.top = "24px";
      tooltip.innerHTML =
        xLabel(s, best) +
        "<br>°C " +
        fmtNum(s.temp_c, 3) +
        "<br>%rF " +
        fmtNum(s.humidity_rh, 2);
      drawChart();
    };
    canvas.onmouseleave = function () {
      state.hover = -1;
      tooltip.hidden = true;
      drawChart();
    };
  }

  function renderTable() {
    var body = $("rows");
    var samples = state.samples.slice().reverse().slice(0, 80);
    body.innerHTML = samples
      .map(function (s, i) {
        var when;
        if (state.source === "history_capture") {
          when = "Index " + (s.index == null ? "—" : s.index);
        } else if (state.source === "history" && s.timestamp) {
          when = fmtTime(s.timestamp);
        } else if (state.source === "history") {
          when = "Index " + (s.index == null ? "—" : s.index);
        } else {
          when = fmtTime(s.timestamp);
        }
        return (
          "<tr><td>" +
          when +
          "</td><td>" +
          fmtNum(s.temp_c, 3) +
          "</td><td>" +
          fmtNum(s.humidity_rh, 2) +
          "</td><td>" +
          (SOURCE_LABELS[s.source] || s.source) +
          "</td></tr>"
        );
      })
      .join("");
    $("table-hint").textContent =
      samples.length === 0 ? "Keine Zeilen." : "Neueste zuerst, max. 80 Zeilen dieser Quelle.";
  }

  function renderChartPanel(payload) {
    var summary = payload.summary || { count: 0 };
    renderKpis(summary);
    var empty = $("empty");
    if (!payload.samples || !payload.samples.length) {
      empty.hidden = false;
      empty.textContent =
        "Keine Daten für diese Quelle. Live: python collector/collect.py — History: python collector/dump_history.py --from-extract hci-logs/extract";
    } else {
      empty.hidden = true;
    }
    $("chart-hint").textContent = SOURCE_HINTS[state.source] || "";
    $("chart-title").textContent = SOURCE_LABELS[state.source] || "Verlauf";
    drawChart();
    renderTable();
  }

  function loadSamples() {
    var room = roomOf(state.overview, state.roomId);
    if (!room) return;
    var limit = state.source && state.source.indexOf("history") === 0 ? 800 : 0;
    var q =
      "/api/samples?mac=" +
      encodeURIComponent(room.mac) +
      "&source=" +
      encodeURIComponent(state.source) +
      "&limit=" +
      limit;
    return api(q).then(function (payload) {
      state.samples = payload.samples || [];
      renderChartPanel(payload);
    });
  }

  function boot() {
    bindChart();
    window.addEventListener("resize", drawChart);
    return api("/api/overview").then(function (ov) {
      state.overview = ov;
      var first = (ov.rooms && ov.rooms[0]) || null;
      state.roomId = first ? first.id : null;
      state.source = pickDefaultSource(first);
      renderMeta();
      renderRooms();
      renderTabs();
      return loadSamples();
    });
  }

  boot().catch(function (err) {
    $("top-meta").textContent = "API-Fehler: " + err.message;
    $("empty").hidden = false;
    $("empty").textContent = "Dashboard-API nicht erreichbar. python dashboard/server.py";
  });
})();
