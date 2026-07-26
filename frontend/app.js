/* VertiBottle dashboard — vanilla JS single-page app.
   Views: overview, per-site dashboard, alerts, USSD simulator, admin.
   Polls the API every POLL_MS (SRS 2.1 step 10: ~30 s). */

"use strict";

const POLL_MS = 30000;
const API = "/api/v1";

/* ---------------- i18n ---------------- */

const STR = {
  en: {
    login_sub: "Hydroponic farm monitoring",
    sign_in: "Sign in", try_role: "Try a role", logout: "Log out",
    username: "Username", password: "Password",
    chip_school: "School operator", chip_cb: "CB operator", chip_coord: "Coordinator",
    chip_agro: "Agronomist", chip_admin: "Administrator",
    banner_alert: "Alert at {site}: {param} is {val}, outside the target band {band}. Action is needed.",
    admin_only: "Admin only.", session_ended: "[session ended]",
    ussd_lang_note: "The phone screen follows the operator's profile language (set via menu option 4), not the dashboard toggle — a CB operator's phone speaks their language regardless of this UI.",
    role: { school_operator: "School operator", cb_operator: "CB operator",
            coordinator: "Coordinator", agronomist: "Agronomist", admin: "Administrator" },
    farm_title: "Live farm",
    farm_all_ok: "All systems running normally — water circulating, sensors reporting.",
    farm_watch: "{param} is drifting — monitoring closely",
    farm_alarm: "{param} out of range — acknowledge the alert to start the fix",
    farm_fixing: "{param}: {action} — value returning to target",
    farm_more: "+{n} more",
    fix_humidity_low: "misting the grow area", fix_humidity_high: "venting excess humidity",
    fix_water_level_low: "refilling the reservoir", fix_water_level_high: "draining excess water",
    fix_ph_low: "dosing pH-up solution", fix_ph_high: "dosing pH-down solution",
    fix_ec_low: "adding nutrient concentrate", fix_ec_high: "diluting with fresh water",
    fix_water_temp_low: "warming the reservoir", fix_water_temp_high: "shading the reservoir",
    fix_air_temp_low: "closing vents to retain heat", fix_air_temp_high: "running the ventilation fan",
    fix_light_low: "removing shade for more light", fix_light_high: "deploying shade cloth",
    twin_title: "Digital twin", twin_live: "live", twin_ok: "All systems nominal — water circulating, sensors reporting.",
    twin_solar: "Solar", twin_batt: "Battery", twin_node: "Node",
    twin_hint: "Drag to orbit · scroll to zoom. Every reading drives the model in real time.",
    twin_nowebgl: "3D view needs WebGL, which this browser has disabled.",
    ussd_pick: "Dial as",
    nav_overview: "Overview", nav_alerts: "Alerts", nav_ussd: "USSD", nav_admin: "Admin",
    overview_title: "Farm sites", overview_sub: "Live status of every bottle farm in the programme",
    school: "School", community: "Community", last_update: "Updated",
    alerts_active: "active alert", alerts_active_pl: "active alerts", no_alerts_site: "All parameters in range",
    back: "Back to overview", target: "Target",
    ribbon_alert: "needs attention", ribbon_watch: "being watched",
    ribbon_fixing: "fix in progress", acknowledge: "Acknowledge",
    alerts_title: "Alerts", alerts_sub: "Active and past alerts across all sites",
    active_section: "Active", history_section: "History",
    col_site: "Site", col_param: "Parameter", col_value: "Value", col_state: "State",
    col_when: "When", col_action: "Action", close: "Close", none_active: "No active alerts. Everything is in range.",
    ussd_title: "USSD simulator", ussd_sub: "The feature-phone experience, no telecom required",
    ussd_hint_title: "How to use it",
    ussd_hint: "Pick an operator above, then Dial as they would on a feature phone. Any registered operator's number works if you type it in.",
    ussd_hint2: "Menu: 1 today's reading · 2 current alerts · 3 acknowledge (dial, 3, then the alert number — three presses) · 4 language · 0 exit.",
    dial: "Dial *384#", send: "Send", end_call: "End",
    admin_title: "Administration", admin_sub: "Sites, operators, audit and the notification outbox",
    register_site: "Register a site", site_name: "Site name", location: "Location",
    crop: "Crop", connectivity: "Connectivity", create: "Create site",
    thresholds: "Crop thresholds", save: "Save", pick_site: "Site",
    operators: "Operators", col_user: "User", col_role: "Role", col_contact: "Contact", col_lang: "Lang", col_site2: "Site",
    outbox: "Notification outbox", outbox_sub: "Email, SMS and USSD sends are simulated — this is what would have gone out.",
    col_channel: "Channel", col_recipient: "Recipient", col_message: "Message", col_status: "Status",
    audit: "Audit log", audit_sub: "Append-only. Every reading, alert and action.",
    node_health: "Node health", col_node: "Node", col_seen: "Last seen", online: "online", offline: "offline",
    all_actions: "All actions", all_channels: "All channels",
    param: { ph: "pH", ec: "EC (µS/cm)", water_temp: "Water temp (°C)", air_temp: "Air temp (°C)",
             humidity: "Humidity (%)", water_level: "Water level (cm)", light: "Light (lux)" },
    state: { watch: "Watch", alert_raised: "Alert raised", notification_sent: "Notification sent",
             acknowledged: "Acknowledged", resolved: "Resolved", closed: "Closed" },
    status: { green: "Healthy", amber: "Watch", red: "Alert", offline: "Offline" },
  },
  fr: {
    login_sub: "Suivi des fermes hydroponiques",
    sign_in: "Connexion", try_role: "Essayer un rôle", logout: "Déconnexion",
    username: "Nom d'utilisateur", password: "Mot de passe",
    chip_school: "Opérateur scolaire", chip_cb: "Opérateur CB", chip_coord: "Coordinateur",
    chip_agro: "Agronome", chip_admin: "Administrateur",
    banner_alert: "Alerte {site} : {param} = {val}, hors de la plage cible {band}. Une intervention est nécessaire.",
    admin_only: "Réservé à l'administrateur.", session_ended: "[session terminée]",
    ussd_lang_note: "L'écran du téléphone suit la langue du profil de l'opérateur (option 4 du menu), pas le sélecteur du tableau de bord — le téléphone d'un opérateur CB parle sa langue quelle que soit cette interface.",
    role: { school_operator: "Opérateur scolaire", cb_operator: "Opérateur CB",
            coordinator: "Coordinateur", agronomist: "Agronome", admin: "Administrateur" },
    farm_title: "Ferme en direct",
    farm_all_ok: "Tous les systèmes fonctionnent — l'eau circule, les capteurs rapportent.",
    farm_watch: "{param} dérive — surveillance renforcée",
    farm_alarm: "{param} hors plage — confirmez l'alerte pour lancer l'intervention",
    farm_fixing: "{param} : {action} — la valeur revient vers la cible",
    farm_more: "+{n} autres",
    fix_humidity_low: "brumisation de la zone de culture", fix_humidity_high: "ventilation de l'humidité",
    fix_water_level_low: "remplissage du réservoir", fix_water_level_high: "vidange du trop-plein",
    fix_ph_low: "dosage de solution pH+", fix_ph_high: "dosage de solution pH-",
    fix_ec_low: "ajout de concentré nutritif", fix_ec_high: "dilution à l'eau claire",
    fix_water_temp_low: "réchauffement du réservoir", fix_water_temp_high: "ombrage du réservoir",
    fix_air_temp_low: "fermeture des aérations", fix_air_temp_high: "ventilation en marche",
    fix_light_low: "retrait de l'ombrage", fix_light_high: "déploiement de la toile d'ombrage",
    twin_title: "Jumeau numérique", twin_live: "en direct", twin_ok: "Tous les systèmes sont nominaux — l'eau circule, les capteurs rapportent.",
    twin_solar: "Solaire", twin_batt: "Batterie", twin_node: "Nœud",
    twin_hint: "Faites glisser pour pivoter · molette pour zoomer. Chaque mesure anime le modèle en temps réel.",
    twin_nowebgl: "La vue 3D nécessite WebGL, désactivé dans ce navigateur.",
    ussd_pick: "Composer en tant que",
    nav_overview: "Vue d'ensemble", nav_alerts: "Alertes", nav_ussd: "USSD", nav_admin: "Admin",
    overview_title: "Sites agricoles", overview_sub: "État en direct de chaque ferme du programme",
    school: "École", community: "Communautaire", last_update: "Mis à jour",
    alerts_active: "alerte active", alerts_active_pl: "alertes actives", no_alerts_site: "Tous les paramètres dans la plage",
    back: "Retour à la vue d'ensemble", target: "Cible",
    ribbon_alert: "demande une intervention", ribbon_watch: "sous surveillance",
    ribbon_fixing: "intervention en cours", acknowledge: "Confirmer",
    alerts_title: "Alertes", alerts_sub: "Alertes actives et passées sur tous les sites",
    active_section: "Actives", history_section: "Historique",
    col_site: "Site", col_param: "Paramètre", col_value: "Valeur", col_state: "État",
    col_when: "Quand", col_action: "Action", close: "Clôturer", none_active: "Aucune alerte active. Tout est dans la plage.",
    ussd_title: "Simulateur USSD", ussd_sub: "L'expérience téléphone simple, sans opérateur télécom",
    ussd_hint_title: "Mode d'emploi",
    ussd_hint: "Choisissez un opérateur ci-dessus, puis composez comme il le ferait sur un téléphone simple. Tout numéro d'opérateur enregistré fonctionne.",
    ussd_hint2: "Menu : 1 relevé du jour · 2 alertes en cours · 3 confirmer (composer, 3, puis le numéro de l'alerte — trois touches) · 4 langue · 0 quitter.",
    dial: "Composer *384#", send: "Envoyer", end_call: "Fin",
    admin_title: "Administration", admin_sub: "Sites, opérateurs, audit et boîte d'envoi",
    register_site: "Enregistrer un site", site_name: "Nom du site", location: "Localité",
    crop: "Culture", connectivity: "Connectivité", create: "Créer le site",
    thresholds: "Seuils de culture", save: "Enregistrer", pick_site: "Site",
    operators: "Opérateurs", col_user: "Utilisateur", col_role: "Rôle", col_contact: "Contact", col_lang: "Langue", col_site2: "Site",
    outbox: "Boîte d'envoi", outbox_sub: "Les envois email, SMS et USSD sont simulés — voici ce qui serait parti.",
    col_channel: "Canal", col_recipient: "Destinataire", col_message: "Message", col_status: "Statut",
    audit: "Journal d'audit", audit_sub: "Inaltérable. Chaque lecture, alerte et action.",
    node_health: "État des nœuds", col_node: "Nœud", col_seen: "Vu le", online: "en ligne", offline: "hors ligne",
    all_actions: "Toutes les actions", all_channels: "Tous les canaux",
    param: { ph: "pH", ec: "CE (µS/cm)", water_temp: "Temp. eau (°C)", air_temp: "Temp. air (°C)",
             humidity: "Humidité (%)", water_level: "Niveau d'eau (cm)", light: "Lumière (lux)" },
    state: { watch: "Surveillance", alert_raised: "Alerte levée", notification_sent: "Notification envoyée",
             acknowledged: "Confirmée", resolved: "Résolue", closed: "Clôturée" },
    status: { green: "Sain", amber: "Surveillance", red: "Alerte", offline: "Hors ligne" },
  },
};

let lang = localStorage.getItem("vb_lang") || "en";
const t = (key) => STR[lang][key] ?? key;

/* ---------------- API helper ---------------- */

let token = localStorage.getItem("vb_token") || null;
let me = JSON.parse(localStorage.getItem("vb_me") || "null");

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) { logout(); throw new Error("unauthorized"); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.status === 204 ? null : res.json();
}

/* ---------------- auth ---------------- */

function showLogin() {
  document.getElementById("login-screen").classList.remove("hidden");
  document.getElementById("app").classList.add("hidden");
  applyI18n();
}

function showApp() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  document.getElementById("whoami").textContent = `${me.name}`;
  document.getElementById("nav-admin").style.display = me.role === "admin" ? "" : "none";
  applyI18n();
  route();
}

function logout() {
  token = null; me = null;
  localStorage.removeItem("vb_token");
  localStorage.removeItem("vb_me");
  showLogin();
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.classList.add("hidden");
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("login-username").value,
        password: document.getElementById("login-password").value,
      }),
    });
    token = data.token; me = data.user;
    localStorage.setItem("vb_token", token);
    localStorage.setItem("vb_me", JSON.stringify(me));
    // Default to the account's profile language, but never override a
    // language the user picked with the toggle themselves.
    if (me.language && !localStorage.getItem("vb_lang_manual")) {
      lang = me.language;
      localStorage.setItem("vb_lang", lang);
    }
    location.hash = "#/overview";
    showApp();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  }
});

document.querySelectorAll(".role-chips .chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.getElementById("login-username").value = chip.dataset.user;
    document.getElementById("login-password").value = "demo1234";
    document.getElementById("login-form").requestSubmit();
  });
});

document.getElementById("logout").addEventListener("click", logout);

/* ---------------- i18n wiring ---------------- */

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.getElementById("lang-toggle").textContent = lang === "en" ? "FR" : "EN";
}

document.getElementById("lang-toggle").addEventListener("click", () => {
  lang = lang === "en" ? "fr" : "en";
  localStorage.setItem("vb_lang", lang);
  // A manual toggle is an explicit choice: stop login from resetting the
  // language to the account's profile language after this.
  localStorage.setItem("vb_lang_manual", "1");
  applyI18n();
  route();
});

/* ---------------- banner (real dashboard notification channel) ---------------- */

// Banners are rendered in the *viewer's* current UI language from the
// notification's structured fields. The stored `message` (fixed in the
// recipient's language at send time) is only a fallback — and remains the
// canonical record shown in the admin outbox.
function bannerText(n) {
  if (!n.parameter) return n.message;
  return t("banner_alert")
    .replace("{site}", n.site_name || "")
    .replace("{param}", t("param")[n.parameter])
    .replace("{val}", n.trigger_value)
    .replace("{band}", `${n.band_min}–${n.band_max}`);
}

async function pollBanners() {
  if (!token) return;
  try {
    const notes = await api("/notifications?unread_only=true&limit=3");
    const area = document.getElementById("banner-area");
    area.innerHTML = "";
    notes.forEach((n) => {
      const div = document.createElement("div");
      div.className = "banner";
      div.innerHTML = `<span>⚠</span><span>${escapeHtml(bannerText(n))}</span>
        <button class="banner-dismiss" title="Dismiss">✕</button>`;
      div.querySelector(".banner-dismiss").addEventListener("click", async () => {
        await api(`/notifications/${n.id}/read`, { method: "POST" });
        div.remove();
      });
      area.appendChild(div);
    });
  } catch (e) { /* polling failure is non-fatal */ }
}

/* ---------------- router ---------------- */

let pollTimer = null;
let charts = [];

function destroyCharts() { charts.forEach((c) => c.destroy()); charts = []; }

function route() {
  if (!token) return;
  destroyCharts();
  if (window.Farm) Farm.unmount();
  if (pollTimer) clearInterval(pollTimer);

  const hash = location.hash || "#/overview";
  document.querySelectorAll(".topnav a").forEach((a) => {
    a.classList.toggle("active", hash.startsWith(a.getAttribute("href")) ||
      (a.getAttribute("href") === "#/overview" && hash.startsWith("#/site/")));
  });

  const view = document.getElementById("view");
  let render;
  if (hash.startsWith("#/site/")) render = () => renderSite(view, hash.split("/")[2]);
  else if (hash.startsWith("#/alerts")) render = () => renderAlerts(view);
  else if (hash.startsWith("#/ussd")) render = () => renderUssd(view);
  else if (hash.startsWith("#/admin")) render = () => renderAdmin(view);
  else render = () => renderOverview(view);

  render();
  pollBanners();
  // USSD and admin pages don't need chart re-renders every 30 s.
  if (!hash.startsWith("#/ussd") && !hash.startsWith("#/admin")) {
    pollTimer = setInterval(() => { render(); pollBanners(); }, POLL_MS);
  } else {
    pollTimer = setInterval(pollBanners, POLL_MS);
  }
}

window.addEventListener("hashchange", route);

/* ---------------- helpers ---------------- */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(lang === "fr" ? "fr-FR" : "en-GB",
    { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(lang === "fr" ? "fr-FR" : "en-GB",
    { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

/* ---------------- overview ---------------- */

async function renderOverview(view) {
  const sites = await api("/sites");
  const mySite = me.site_id;
  view.innerHTML = `
    <h1 class="page-title">${t("overview_title")}</h1>
    <p class="page-sub">${t("overview_sub")}</p>
    <div class="site-grid"></div>`;
  const grid = view.querySelector(".site-grid");
  sites
    .sort((a, b) => (a.id === mySite ? -1 : b.id === mySite ? 1 : 0))
    .forEach((s) => {
      const a = document.createElement("a");
      a.className = "site-card";
      a.href = `#/site/${s.id}`;
      const typeLabel = s.site_type === "school" ? t("school") : t("community");
      const alertsLine = s.active_alerts > 0
        ? `${s.active_alerts} ${s.active_alerts > 1 ? t("alerts_active_pl") : t("alerts_active")}`
        : t("no_alerts_site");
      a.innerHTML = `
        <div class="status-row">
          <span class="traffic ${s.status}"></span>
          <span class="status-label ${s.status}">${t("status")[s.status]}</span>
        </div>
        <h3>${escapeHtml(s.name)}</h3>
        <p class="meta">${typeLabel} · ${escapeHtml(s.location)} · ${escapeHtml(s.crop_name)}<br>
          ${alertsLine}<br>
          <span class="muted">${t("last_update")} ${fmtTime(s.last_updated)}</span></p>`;
      grid.appendChild(a);
    });
}

/* ---------------- per-site dashboard ---------------- */

// Chart.js plugin: shade the crop's target band in light green across the
// plot area, so "healthy" is visible at a glance.
const bandPlugin = {
  id: "band",
  beforeDatasetsDraw(chart, args, opts) {
    if (opts.min == null) return;
    const { ctx, chartArea, scales } = chart;
    const y1 = scales.y.getPixelForValue(opts.max);
    const y2 = scales.y.getPixelForValue(opts.min);
    ctx.save();
    ctx.fillStyle = "rgba(47, 158, 95, 0.10)";
    ctx.fillRect(chartArea.left, y1, chartArea.right - chartArea.left, y2 - y1);
    ctx.restore();
  },
};

async function renderSite(view, siteId) {
  const [site, series, alerts] = await Promise.all([
    api(`/sites/${siteId}`),
    api(`/readings?site_id=${siteId}&hours=24`),
    api(`/alerts?site_id=${siteId}&active=true`),
  ]);

  // Build the skeleton (and the animated farm scene) only when arriving at
  // this site; poll ticks update in place so CSS animations never reset.
  const rebuild = charts.length === 0 || view.dataset.siteId !== siteId;
  if (rebuild) {
    destroyCharts();
    if (window.Farm) Farm.unmount();
    view.dataset.siteId = siteId;
    view.innerHTML = `
      <a class="back-link" href="#/overview">← ${t("back")}</a>
      <div class="site-header">
        <h1 class="page-title">${escapeHtml(site.name)}</h1>
        <span class="muted">${escapeHtml(site.location)} · ${escapeHtml(site.crop_name)}</span>
      </div>
      <p class="page-sub">${site.site_type === "school" ? t("school") : t("community")}
        · <span id="site-updated"></span></p>
      <div id="site-ribbon"></div>
      <div id="farm-panel" class="farm-panel"></div>
      <div class="chart-grid"></div>`;

    const grid = view.querySelector(".chart-grid");
    series.forEach((s) => {
      const card = document.createElement("div");
      card.className = "chart-card";
      card.innerHTML = `
        <div class="chart-head">
          <h3>${t("param")[s.parameter]}</h3>
          <span class="value-badge" id="badge-${s.parameter}">—</span>
        </div>
        <p class="band-note">${t("target")}: ${s.band_min} – ${s.band_max}</p>
        <div class="chart-wrap"><canvas></canvas></div>`;
      grid.appendChild(card);

      const chart = new Chart(card.querySelector("canvas"), {
        type: "line",
        data: {
          datasets: [{
            data: [],
            borderColor: "#2f6fa8",
            borderWidth: 1.6,
            pointRadius: 0,
            tension: 0.3,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { display: false },
            band: { min: s.band_min, max: s.band_max },
            tooltip: { intersect: false, mode: "index" },
          },
          scales: {
            x: {
              type: "linear",
              ticks: {
                maxTicksLimit: 6,
                callback: (v) => new Date(v).toLocaleTimeString(lang === "fr" ? "fr-FR" : "en-GB",
                  { hour: "2-digit", minute: "2-digit" }),
              },
              grid: { display: false },
            },
            y: { grid: { color: "#f0f0f2" } },
          },
        },
        plugins: [bandPlugin],
      });
      chart._param = s.parameter;
      charts.push(chart);
    });
    if (window.Farm) Farm.mount(document.getElementById("farm-panel"), site);
  }

  // Update pass (runs on first render and every poll).
  document.getElementById("site-updated").textContent =
    `${t("last_update")} ${fmtTime(site.last_updated)}`;
  document.getElementById("site-ribbon").innerHTML = buildRibbon(alerts);
  wireRibbon(view, () => renderSite(view, siteId));

  series.forEach((s) => {
    const chart = charts.find((c) => c._param === s.parameter);
    if (chart) {
      chart.data.datasets[0].data =
        s.points.map((p) => ({ x: new Date(p.ts).getTime(), y: p.value }));
      chart.update("none");
    }
    const badge = document.getElementById(`badge-${s.parameter}`);
    if (badge) {
      badge.textContent = s.latest ?? "—";
      badge.className = "value-badge " + (s.in_band === null ? "" : s.in_band ? "in" : "out");
    }
  });
  if (window.Farm) Farm.push(series, alerts);
}

function buildRibbon(alerts) {
  const live = alerts.filter((a) =>
    ["alert_raised", "notification_sent", "acknowledged", "watch"].includes(a.state));
  if (live.length === 0) return "";
  // Priority: an un-acknowledged alarm needs a human now; a fix in progress
  // outranks a mere Watch because it's the one the farm view is animating.
  const rank = (a) => (["alert_raised", "notification_sent"].includes(a.state) ? 0
    : a.state === "acknowledged" ? 1 : 2);
  const worst = [...live].sort((a, b) => rank(a) - rank(b))[0];
  const cls = rank(worst) === 0 ? "red" : rank(worst) === 1 ? "blue" : "amber";
  const verb = cls === "red" ? t("ribbon_alert")
    : cls === "blue" ? t("ribbon_fixing") : t("ribbon_watch");
  const canAck = worst.state === "notification_sent" &&
    (me.role === "admin" || me.role === "coordinator" || me.site_id === worst.site_id);
  return `
    <div class="alert-ribbon ${cls}" data-alert-id="${worst.id}">
      <strong>${t("param")[worst.parameter]}</strong>
      <span>${worst.trigger_value} (${t("target")} ${worst.band_min}–${worst.band_max}) — ${verb}</span>
      <span class="state-pill ${worst.state}">${t("state")[worst.state]}</span>
      ${canAck ? `<button class="ack-btn">${t("acknowledge")}</button>` : ""}
    </div>`;
}

function wireRibbon(view, refresh) {
  const btn = view.querySelector(".alert-ribbon .ack-btn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const id = view.querySelector(".alert-ribbon").dataset.alertId;
    await api(`/alerts/${id}/ack`, { method: "POST" });
    refresh();
  });
}

/* ---------------- alerts view ---------------- */

async function renderAlerts(view) {
  const all = await api("/alerts?limit=100");
  const active = all.filter((a) =>
    ["watch", "alert_raised", "notification_sent", "acknowledged"].includes(a.state));
  const past = all.filter((a) => ["resolved", "closed"].includes(a.state));

  const canClose = me.role === "admin" || me.role === "coordinator";

  const row = (a, showAction) => {
    const canAck = a.state === "notification_sent" &&
      (canClose || me.site_id === a.site_id);
    const canCloseThis = canClose && a.state === "resolved";
    let action = "";
    if (showAction && canAck) action = `<button class="link-btn" data-ack="${a.id}">${t("acknowledge")}</button>`;
    else if (showAction && canCloseThis) action = `<button class="link-btn" data-close="${a.id}">${t("close")}</button>`;
    return `<tr>
      <td>${escapeHtml(a.site_name || a.site_id)}</td>
      <td>${t("param")[a.parameter]}</td>
      <td>${a.trigger_value} <span class="muted">(${a.band_min}–${a.band_max})</span></td>
      <td><span class="state-pill ${a.state}">${t("state")[a.state]}</span></td>
      <td class="muted">${fmtDateTime(a.created_at)}</td>
      <td>${action}</td>
    </tr>`;
  };

  const table = (rows) => `
    <div class="table-scroll"><table class="table">
      <thead><tr>
        <th>${t("col_site")}</th><th>${t("col_param")}</th><th>${t("col_value")}</th>
        <th>${t("col_state")}</th><th>${t("col_when")}</th><th>${t("col_action")}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;

  view.innerHTML = `
    <h1 class="page-title">${t("alerts_title")}</h1>
    <p class="page-sub">${t("alerts_sub")}</p>
    <div class="section">
      <h2>${t("active_section")}</h2>
      ${active.length ? table(active.map((a) => row(a, true)).join(""))
        : `<p class="empty">${t("none_active")}</p>`}
    </div>
    <div class="section">
      <h2>${t("history_section")}</h2>
      ${past.length ? table(past.map((a) => row(a, true)).join("")) : `<p class="empty">—</p>`}
    </div>`;

  view.querySelectorAll("[data-ack]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/alerts/${b.dataset.ack}/ack`, { method: "POST" });
      renderAlerts(view);
    }));
  view.querySelectorAll("[data-close]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/alerts/${b.dataset.close}/close`, { method: "POST" });
      renderAlerts(view);
    }));
}

/* ---------------- USSD simulator ---------------- */

// The phone's language is the *operator profile's* language (a feature
// phone has no dashboard toggle), so the demo defaults to an operator who
// matches the current UI language — English UI dials as Aissatou (en),
// French UI as Falmata (fr).
const USSD_DEMO_OPERATORS = [
  { phone: "+237650000001", label: "Aissatou · EN · GSS Maroua", lang: "en" },
  { phone: "+237650000002", label: "Falmata · FR · Makabay", lang: "fr" },
];

function renderUssd(view) {
  const defaultOp = USSD_DEMO_OPERATORS.find((o) => o.lang === lang) || USSD_DEMO_OPERATORS[0];
  view.innerHTML = `
    <h1 class="page-title">${t("ussd_title")}</h1>
    <p class="page-sub">${t("ussd_sub")}</p>
    <div class="ussd-wrap">
      <div class="phone">
        <p class="ussd-pick-label">${t("ussd_pick")}</p>
        <div class="role-chips ussd-ops">
          ${USSD_DEMO_OPERATORS.map((o) =>
            `<button class="chip ${o.phone === defaultOp.phone ? "active" : ""}"
                     data-phone="${o.phone}">${o.label}</button>`).join("")}
        </div>
        <div class="phone-screen" id="ussd-screen">*384#</div>
        <div class="phone-input">
          <input id="ussd-phone" placeholder="${defaultOp.phone}" value="${defaultOp.phone}">
        </div>
        <div class="keypad" id="ussd-keypad"></div>
        <div class="phone-actions">
          <button class="dial-btn" id="ussd-dial">${t("dial")}</button>
          <button class="send-btn" id="ussd-send">${t("send")}</button>
          <button class="end-btn" id="ussd-end">${t("end_call")}</button>
        </div>
      </div>
      <div class="ussd-side">
        <h2>${t("ussd_hint_title")}</h2>
        <p>${t("ussd_hint")}</p>
        <br><p>${t("ussd_hint2")}</p>
        <br><p class="muted">${t("ussd_lang_note")}</p>
      </div>
    </div>`;

  const screen = document.getElementById("ussd-screen");
  const keypad = document.getElementById("ussd-keypad");
  let sessionKeys = [];   // accumulated presses this session
  let pending = "";       // digits typed since last Send
  let sessionActive = false;

  view.querySelectorAll(".ussd-ops .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.getElementById("ussd-phone").value = chip.dataset.phone;
      view.querySelectorAll(".ussd-ops .chip").forEach((c) =>
        c.classList.toggle("active", c === chip));
      sessionActive = false; sessionKeys = []; pending = "";
      screen.textContent = "*384#";
    });
  });

  ["1","2","3","4","5","6","7","8","9","*","0","#"].forEach((k) => {
    const b = document.createElement("button");
    b.textContent = k;
    b.addEventListener("click", () => {
      if (!sessionActive) return;
      pending += k;
      screen.textContent += k;
    });
    keypad.appendChild(b);
  });

  async function callUssd() {
    const phone = document.getElementById("ussd-phone").value.trim();
    const text = sessionKeys.join("*");
    try {
      const res = await api("/ussd", { method: "POST", body: JSON.stringify({ phone, text }) });
      screen.textContent = res.message;
      if (res.end) { sessionActive = false; screen.textContent += "\n\n" + t("session_ended"); }
    } catch (e) {
      screen.textContent = "Network error: " + e.message;
      sessionActive = false;
    }
  }

  document.getElementById("ussd-dial").addEventListener("click", () => {
    sessionKeys = []; pending = ""; sessionActive = true;
    callUssd();
  });
  document.getElementById("ussd-send").addEventListener("click", () => {
    if (!sessionActive || pending === "") return;
    sessionKeys.push(pending);
    pending = "";
    callUssd();
  });
  document.getElementById("ussd-end").addEventListener("click", () => {
    sessionActive = false; sessionKeys = []; pending = "";
    screen.textContent = "*384#";
  });
}

/* ---------------- admin ---------------- */

async function renderAdmin(view) {
  if (me.role !== "admin") { view.innerHTML = `<p class="empty">${t("admin_only")}</p>`; return; }

  const [sites, crops, users, outbox, audit, health] = await Promise.all([
    api("/sites"), api("/crops"), api("/admin/users"),
    api("/notifications/outbox?limit=40"), api("/admin/audit?limit=60"), api("/admin/health"),
  ]);

  const cropOpts = crops.map((c) => `<option value="${c.crop_name}">${c.crop_name}</option>`).join("");
  const siteOpts = sites.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("");

  view.innerHTML = `
    <h1 class="page-title">${t("admin_title")}</h1>
    <p class="page-sub">${t("admin_sub")}</p>

    <div class="section">
      <h2>${t("register_site")}</h2>
      <form id="site-form">
        <div class="form-grid">
          <input name="name" placeholder="${t("site_name")}" required>
          <input name="location" placeholder="${t("location")}" required>
          <select name="site_type"><option value="school">${t("school")}</option>
            <option value="community">${t("community")}</option></select>
          <select name="crop_name">${cropOpts}</select>
          <select name="connectivity"><option value="wifi">Wi-Fi</option><option value="gsm">GSM</option></select>
        </div>
        <button class="btn-secondary">${t("create")}</button>
        <div id="site-form-msg"></div>
      </form>
    </div>

    <div class="section">
      <h2>${t("thresholds")}</h2>
      <div class="filter-row">
        <select id="th-site">${siteOpts}</select>
      </div>
      <form id="th-form"><div class="form-grid" id="th-fields"></div>
        <button class="btn-secondary">${t("save")}</button>
        <div id="th-msg"></div>
      </form>
    </div>

    <div class="section">
      <h2>${t("node_health")}</h2>
      <div class="table-scroll"><table class="table"><thead><tr>
        <th>${t("col_site")}</th><th>${t("col_node")}</th><th>${t("connectivity")}</th><th>${t("col_seen")}</th><th></th>
      </tr></thead><tbody>
      ${health.map((h) => `<tr>
        <td>${escapeHtml(h.site_name)}</td>
        <td class="mono">${h.node_id.slice(0, 8)}</td>
        <td>${h.connectivity}</td>
        <td class="muted">${fmtDateTime(h.last_seen)}</td>
        <td><span class="online-dot ${h.online ? "on" : "off"}"></span>${h.online ? t("online") : t("offline")}</td>
      </tr>`).join("")}
      </tbody></table></div>
    </div>

    <div class="section">
      <h2>${t("operators")}</h2>
      <div class="table-scroll"><table class="table"><thead><tr>
        <th>${t("col_user")}</th><th>${t("col_role")}</th><th>${t("col_contact")}</th>
        <th>${t("col_lang")}</th><th>${t("col_site2")}</th>
      </tr></thead><tbody>
      ${users.map((u) => `<tr>
        <td>${escapeHtml(u.name)}<br><span class="muted mono">${u.username}</span></td>
        <td>${t("role")[u.role] || u.role}</td>
        <td class="muted">${u.phone || ""}<br>${u.email || ""}</td>
        <td>${u.language}</td>
        <td class="muted">${escapeHtml(sites.find((s) => s.id === u.site_id)?.name || "—")}</td>
      </tr>`).join("")}
      </tbody></table></div>
    </div>

    <div class="section">
      <h2>${t("outbox")}</h2>
      <p class="page-sub">${t("outbox_sub")}</p>
      <div class="table-scroll"><table class="table"><thead><tr>
        <th>${t("col_channel")}</th><th>${t("col_recipient")}</th>
        <th>${t("col_message")}</th><th>${t("col_status")}</th><th>${t("col_when")}</th>
      </tr></thead><tbody>
      ${outbox.map((n) => `<tr>
        <td><span class="state-pill ${n.channel === "dashboard" ? "resolved" : "acknowledged"}">${n.channel}</span></td>
        <td class="mono">${escapeHtml(n.recipient)}</td>
        <td>${escapeHtml(n.message)}</td>
        <td class="muted">${n.status}</td>
        <td class="muted">${fmtDateTime(n.sent_at)}</td>
      </tr>`).join("")}
      </tbody></table></div>
    </div>

    <div class="section">
      <h2>${t("audit")}</h2>
      <p class="page-sub">${t("audit_sub")}</p>
      <div class="filter-row">
        <select id="audit-filter">
          <option value="">${t("all_actions")}</option>
          ${[...new Set(audit.map((a) => a.action))].map((a) => `<option>${a}</option>`).join("")}
        </select>
      </div>
      <div class="table-scroll"><table class="table"><tbody id="audit-body"></tbody></table></div>
    </div>`;

  // register site
  document.getElementById("site-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const msg = document.getElementById("site-form-msg");
    try {
      await api("/sites", { method: "POST", body: JSON.stringify(Object.fromEntries(f)) });
      msg.innerHTML = `<p class="notice">✓</p>`;
      renderAdmin(view);
    } catch (err) {
      msg.innerHTML = `<p class="notice error">${escapeHtml(err.message)}</p>`;
    }
  });

  // thresholds editor
  const thFields = document.getElementById("th-fields");
  const thSite = document.getElementById("th-site");
  async function loadThresholds() {
    const detail = await api(`/sites/${thSite.value}`);
    const p = detail.crop_profile;
    const fields = ["ph_min","ph_max","ec_min","ec_max","water_temp_min","water_temp_max",
      "air_temp_min","air_temp_max","humidity_min","humidity_max",
      "water_level_min","water_level_max","light_min","light_max"];
    thFields.innerHTML = fields.map((f) =>
      `<input name="${f}" type="number" step="any" value="${p[f]}" title="${f}" placeholder="${f}">`).join("");
  }
  thSite.addEventListener("change", loadThresholds);
  await loadThresholds();

  document.getElementById("th-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {};
    new FormData(e.target).forEach((v, k) => { if (v !== "") body[k] = parseFloat(v); });
    const msg = document.getElementById("th-msg");
    try {
      await api(`/sites/${thSite.value}/thresholds`, { method: "PATCH", body: JSON.stringify(body) });
      msg.innerHTML = `<p class="notice">✓</p>`;
    } catch (err) {
      msg.innerHTML = `<p class="notice error">${escapeHtml(err.message)}</p>`;
    }
  });

  // audit table w/ filter
  const auditBody = document.getElementById("audit-body");
  function drawAudit(filter) {
    const rows = audit.filter((a) => !filter || a.action === filter);
    auditBody.innerHTML = rows.map((a) => `<tr>
      <td class="muted mono">${fmtDateTime(a.ts)}</td>
      <td class="mono">${escapeHtml(a.actor)}</td>
      <td><span class="state-pill closed">${a.action}</span></td>
      <td class="muted">${escapeHtml(a.detail)}</td>
    </tr>`).join("");
  }
  document.getElementById("audit-filter").addEventListener("change", (e) => drawAudit(e.target.value));
  drawAudit("");
}

/* ---------------- boot ---------------- */

// Kiosk/demo helpers: ?auto=<username> signs in with the demo password and
// ?lang=en|fr forces the UI language. Handy for projector setups and
// headless screenshots; harmless otherwise.
const bootParams = new URLSearchParams(location.search);
const forcedLang = bootParams.get("lang");
if (forcedLang === "en" || forcedLang === "fr") {
  lang = forcedLang;
  localStorage.setItem("vb_lang", lang);
  localStorage.setItem("vb_lang_manual", "1");  // an explicit choice, like the toggle
}
const autoUser = bootParams.get("auto");
if (autoUser) {
  api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username: autoUser, password: "demo1234" }),
  }).then((data) => {
    token = data.token; me = data.user;
    localStorage.setItem("vb_token", token);
    localStorage.setItem("vb_me", JSON.stringify(me));
    showApp();
  }).catch(showLogin);
} else if (token && me) showApp(); else showLogin();
