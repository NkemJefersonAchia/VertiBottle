/* Live farm view — an animated SVG rendering of one bottle farm, driven by
   the same readings the charts use.

   Always-on animations show the farm "running": water circulating through
   the pipe, plants swaying, sun intensity tracking the light reading, the
   reservoir level and tint tracking water level and EC. Out-of-band
   parameters flash their subsystem amber (Watch) or red (raised alert).
   When an alert is ACKNOWLEDGED the matching corrective-action overlay
   plays (misting, refilling, dosing, shading, fan...) while the backend's
   recovery ramp actually brings the value home — the animation and the
   data agree.

   Depends on globals from app.js: api(), t(), lang, escapeHtml(). */

"use strict";

const Farm = (() => {
  let rootEl = null;
  let site = null;
  let timer = null;

  const clamp01 = (x) => Math.max(0, Math.min(1, x));
  const norm = (v, lo, hi) => (v - lo) / (hi - lo);

  function mix(hexA, hexB, k) {
    const a = hexA.match(/\w\w/g).map((h) => parseInt(h, 16));
    const b = hexB.match(/\w\w/g).map((h) => parseInt(h, 16));
    return "#" + a.map((x, i) => Math.round(x + (b[i] - x) * k)
      .toString(16).padStart(2, "0")).join("");
  }

  /* ---------- scene ---------- */

  function bottle(x, y) {
    return `
      <g class="bottle" transform="translate(${x},${y})">
        <rect x="6" y="-10" width="24" height="12" rx="4" class="bottle-neck"/>
        <rect x="0" y="0" width="36" height="52" rx="12" class="bottle-body"/>
        <ellipse class="leaf leaf-l" cx="-8" cy="12" rx="16" ry="7"/>
        <ellipse class="leaf leaf-r" cx="44" cy="16" rx="16" ry="7"/>
        <ellipse class="leaf leaf-l2" cx="-5" cy="30" rx="12" ry="5"/>
        <ellipse class="leaf leaf-r2" cx="41" cy="34" rx="12" ry="5"/>
      </g>`;
  }

  function thermometer(id, x, y) {
    return `
      <g id="${id}" transform="translate(${x},${y})">
        <rect x="-4" y="0" width="8" height="52" rx="4" class="thermo-track"/>
        <rect x="-2.5" y="24" width="5" height="26" rx="2.5" class="thermo-fill"/>
        <circle cx="0" cy="56" r="8" class="thermo-bulb"/>
      </g>`;
  }

  function sceneHTML() {
    const bottles = [0, 1, 2, 3].map((i) => bottle(196, 96 + i * 64)).join("");
    const mist = [0, 1, 2, 3, 4].map((i) =>
      `<circle class="mist-drop d${i}" cx="${150 + i * 42}" cy="${90 + (i % 3) * 24}" r="3.4"/>`).join("");
    const bubbles = [0, 1, 2].map((i) =>
      `<circle class="flow-bubble b${i}" cx="278" cy="330" r="4"/>`).join("");
    const tankBubbles = [0, 1].map((i) =>
      `<circle class="tank-bubble tb${i}" cx="${500 + i * 60}" cy="366" r="3"/>`).join("");

    return `
    <div class="farm-head">
      <h2>${t("farm_title")}</h2>
      <span class="tick-dot" id="farm-tick"></span>
    </div>
    <svg id="farm-svg" viewBox="0 0 900 430" role="img" aria-label="${t("farm_title")}">
      <!-- sun + light -->
      <g id="farm-sun" transform="translate(795,88)">
        <g id="sun-rays">${[...Array(8)].map((_, i) =>
          `<line x1="0" y1="-40" x2="0" y2="-52" transform="rotate(${i * 45})"/>`).join("")}
        </g>
        <circle r="27" class="sun-core"/>
      </g>
      <g id="fix-light" class="fix" transform="translate(752,30)">
        <rect width="86" height="14" rx="7" class="shade-cloth"/>
        <rect y="18" width="86" height="14" rx="7" class="shade-cloth"/>
      </g>

      <!-- humidity mist -->
      <g id="farm-mist">${mist}</g>
      <g id="fix-humidity" class="fix" transform="translate(120,70)">
        <rect x="-6" y="-14" width="26" height="14" rx="4" class="fix-device"/>
        ${[0, 1, 2].map((i) => `<circle class="spray s${i}" cx="7" cy="4" r="5"/>`).join("")}
      </g>

      <!-- grow column -->
      <rect x="188" y="86" width="52" height="286" rx="10" class="column-back"/>
      ${bottles}
      ${thermometer("farm-air-thermo", 330, 130)}
      <g id="fix-air_temp" class="fix" transform="translate(318,220)">
        <circle r="16" class="fan-ring"/>
        <g class="fan-blades">
          ${[0, 1, 2].map((_, i) => `<ellipse cx="0" cy="-8" rx="4" ry="8" transform="rotate(${i * 120})"/>`).join("")}
        </g>
      </g>

      <!-- pipe + pump -->
      <path d="M 430 330 L 306 330 L 306 348" class="pipe"/>
      <path d="M 278 348 L 278 96 L 240 96" class="pipe"/>
      ${bubbles}
      <g id="farm-pump" transform="translate(292,352)">
        <rect x="-22" y="-4" width="44" height="26" rx="7" class="pump-body"/>
        <circle cx="0" cy="9" r="8" class="pump-wheel"/>
      </g>

      <!-- reservoir -->
      <g id="farm-tank">
        <rect x="430" y="268" width="212" height="112" rx="14" class="tank-shell"/>
        <clipPath id="tank-clip"><rect x="434" y="272" width="204" height="104" rx="11"/></clipPath>
        <g clip-path="url(#tank-clip)">
          <rect id="farm-water" x="434" y="300" width="204" height="80"/>
          ${tankBubbles}
        </g>
        ${thermometer("farm-water-thermo", 614, 288)}
        <g id="farm-ph-chip" transform="translate(452,286)">
          <rect width="64" height="24" rx="12" class="ph-chip-bg"/>
          <text id="farm-ph-text" x="32" y="16">pH —</text>
        </g>
      </g>
      <g id="fix-water_level" class="fix" transform="translate(560,214)">
        <rect x="-12" y="0" width="34" height="12" rx="5" class="fix-device"/>
        <line class="pour" x1="4" y1="14" x2="4" y2="58"/>
      </g>
      <g id="fix-ph" class="fix" transform="translate(470,220)">
        <path d="M 0 0 h 16 l -4 12 h -8 z" class="fix-device"/>
        ${[0, 1].map((i) => `<circle class="drip p${i}" cx="8" cy="18" r="3"/>`).join("")}
      </g>
      <g id="fix-ec" class="fix" transform="translate(600,208)">
        <rect x="-8" y="-4" width="28" height="20" rx="6" class="nutrient-bag"/>
        ${[0, 1].map((i) => `<circle class="drip n${i}" cx="6" cy="22" r="3"/>`).join("")}
      </g>
      <g id="fix-water_temp" class="fix" transform="translate(430,244)">
        <rect width="212" height="12" rx="6" class="shade-cloth"/>
      </g>

      <!-- ground -->
      <line x1="60" y1="392" x2="840" y2="392" class="ground"/>

      <!-- fixing badge -->
      <g id="fix-badge" class="fix" transform="translate(76,66)">
        <circle r="20" class="badge-ring"/>
        <path class="badge-wrench" d="M -7 6 L 2 -3 a 6 6 0 1 1 4 4 L -3 10 z"/>
      </g>
    </svg>
    <p id="farm-caption" class="farm-caption"></p>
    <div id="farm-chips" class="farm-chips"></div>`;
  }

  /* ---------- data -> visuals ---------- */

  const FLASH_TARGETS = {
    ph: "farm-ph-chip", ec: "farm-water", water_temp: "farm-water-thermo",
    air_temp: "farm-air-thermo", humidity: "farm-mist",
    water_level: "farm-water", light: "farm-sun",
  };

  function paramStates(alerts) {
    // param -> {kind: watch|alarm|fixing, direction: 1|-1}
    const states = {};
    alerts.forEach((a) => {
      const direction = a.trigger_value > a.band_max ? 1 : -1;
      if (a.state === "acknowledged") states[a.parameter] = { kind: "fixing", direction };
      else if (a.state === "watch") states[a.parameter] = states[a.parameter] || { kind: "watch", direction };
      else states[a.parameter] = { kind: "alarm", direction };
    });
    return states;
  }

  function update(series, alerts) {
    if (!rootEl || !document.getElementById("farm-svg")) return;
    const by = {};
    series.forEach((s) => { by[s.parameter] = s; });
    const states = paramStates(alerts);
    const el = (id) => document.getElementById(id);

    // Sun follows light.
    const sLight = by.light;
    if (sLight && sLight.latest != null) {
      const n = clamp01(norm(sLight.latest, sLight.band_min, sLight.band_max));
      el("farm-sun").style.opacity = 0.35 + 0.65 * n;
      el("sun-rays").style.transform = `scale(${0.75 + 0.5 * n})`;
    }

    // Reservoir level + EC tint.
    const sLevel = by.water_level, sEc = by.ec;
    if (sLevel && sLevel.latest != null) {
      const h = 14 + 88 * clamp01(norm(sLevel.latest, sLevel.band_min, sLevel.band_max));
      const water = el("farm-water");
      water.setAttribute("y", 376 - h);
      water.setAttribute("height", h);
    }
    if (sEc && sEc.latest != null) {
      el("farm-water").style.fill =
        mix("4a86c2", "2f9e7f", clamp01(norm(sEc.latest, sEc.band_min, sEc.band_max)));
    }

    // Thermometers.
    [["water_temp", "farm-water-thermo"], ["air_temp", "farm-air-thermo"]].forEach(([p, id]) => {
      const s = by[p];
      if (!s || s.latest == null) return;
      const h = 10 + 38 * clamp01(norm(s.latest, s.band_min, s.band_max));
      const fill = el(id).querySelector(".thermo-fill");
      fill.setAttribute("height", h);
      fill.setAttribute("y", 52 - h);
    });

    // Humidity mist density.
    const sHum = by.humidity;
    if (sHum && sHum.latest != null) {
      el("farm-mist").style.opacity =
        0.12 + 0.88 * clamp01(norm(sHum.latest, sHum.band_min, sHum.band_max));
    }

    // pH chip.
    const sPh = by.ph;
    if (sPh && sPh.latest != null) el("farm-ph-text").textContent = `pH ${sPh.latest}`;

    // Flash sick subsystems; play fix overlays.
    let anyFixing = false;
    Object.keys(FLASH_TARGETS).forEach((p) => {
      const target = el(FLASH_TARGETS[p]);
      const st = states[p];
      target.classList.remove("out-amber", "out-red");
      if (st && st.kind === "watch") target.classList.add("out-amber");
      if (st && st.kind === "alarm") target.classList.add("out-red");
      const fix = el(`fix-${p}`);
      if (fix) {
        const active = !!st && st.kind === "fixing";
        fix.classList.toggle("active", active);
        anyFixing = anyFixing || active;
      }
    });
    el("fix-badge").classList.toggle("active", anyFixing);

    // Caption: worst issue wins (alarm > fixing > watch > all-clear).
    el("farm-caption").innerHTML = caption(by, states);

    // Parameter chips.
    el("farm-chips").innerHTML = series.map((s) => {
      const st = states[s.parameter];
      const cls = !st ? "ok" : st.kind === "watch" ? "watch" : st.kind === "fixing" ? "fixing" : "alarm";
      return `<span class="farm-chip ${cls}"><span class="dot"></span>
        ${t("param")[s.parameter]} · <strong>${s.latest ?? "—"}</strong></span>`;
    }).join("");

    // Heartbeat blink so it's obvious the view is live.
    const tick = el("farm-tick");
    tick.classList.remove("blink");
    void tick.offsetWidth;  // restart the animation
    tick.classList.add("blink");
  }

  function caption(by, states) {
    const rank = { alarm: 0, fixing: 1, watch: 2 };
    const issues = Object.entries(states)
      .sort((a, b) => rank[a[1].kind] - rank[b[1].kind]);
    if (issues.length === 0) return `<span class="cap-ok">${t("farm_all_ok")}</span>`;

    const [param, st] = issues[0];
    const label = t("param")[param];
    const value = by[param] && by[param].latest != null ? ` (${by[param].latest})` : "";
    const more = issues.length > 1
      ? ` <span class="muted">${t("farm_more").replace("{n}", issues.length - 1)}</span>` : "";

    if (st.kind === "fixing") {
      const action = t(`fix_${param}_${st.direction > 0 ? "high" : "low"}`);
      return `<span class="cap-fixing">${t("farm_fixing").replace("{param}", label)
        .replace("{action}", action)}${value}</span>${more}`;
    }
    if (st.kind === "alarm") {
      return `<span class="cap-alarm">${t("farm_alarm").replace("{param}", label)}${value}</span>${more}`;
    }
    return `<span class="cap-watch">${t("farm_watch").replace("{param}", label)}${value}</span>${more}`;
  }

  /* ---------- lifecycle ---------- */

  async function refresh() {
    if (!rootEl || !site) return;
    try {
      const [series, alerts] = await Promise.all([
        api(`/readings?site_id=${site.id}&hours=1`),
        api(`/alerts?site_id=${site.id}&active=true`),
      ]);
      update(series, alerts);
    } catch (e) { /* transient poll failure: keep the last frame */ }
  }

  function mount(containerEl, siteObj) {
    unmount();
    rootEl = containerEl;
    site = siteObj;
    rootEl.innerHTML = sceneHTML();
    // The farm refreshes faster than the 30 s chart poll: the simulator
    // ticks every ~10 s and the fix animations should track it closely.
    timer = setInterval(refresh, 10000);
  }

  function push(series, alerts) { update(series, alerts); }

  function unmount() {
    if (timer) clearInterval(timer);
    timer = null;
    rootEl = null;
    site = null;
  }

  return { mount, unmount, push, refresh };
})();
