/*
 * HEMS panel and cards for Home Assistant. One self-contained ES module without dependencies or a build step.
 *
 *  - <hems-panel>          the sidebar panel (registered by custom_components/hems/panel.py)
 *  - <hems-timeline-card>  Lovelace card: the shared time axis (type: custom:hems-timeline-card, hours: 24)
 *  - <hems-verdict-card>   Lovelace card: what HEMS would do now and why
 *
 * Data: the websocket subscription `hems/subscribe` (the whole horizon, pushed after every cycle) and `hems/settings`;
 * live power comes straight from the entities of the roles in the settings. Nothing here writes to a device: the only
 * action is the EV override switch, behind an inline confirmation.
 *
 * URL options: ?kiosk (no header, for the wall tablet), ?theme=dark|light (force a theme), #nu|plan|prijzen|batterij|auto|boiler|net|regie.
 */

const VERSION = "0.3.0";
const Q_MS = 15 * 60 * 1000;

/* ------------------------------------------------------------------ store */

class HemsStore {
  constructor() {
    this.payload = null;
    this.loaded = null;
    this.settings = null;
    this.error = null;
    this.listeners = new Set();
    this._conn = null;
    this._unsub = null;
  }

  attach(hass) {
    if (!hass || !hass.connection) return;
    if (this._conn === hass.connection) return;
    this._conn = hass.connection;
    if (this._unsub) { try { this._unsub(); } catch (e) { /* connection gone */ } }
    this._unsub = null;
    hass.connection.subscribeMessage((msg) => {
      this.loaded = msg.loaded;
      this.payload = msg.payload;
      this.receivedAt = Date.now();
      this.error = null;
      this._emit();
    }, { type: "hems/subscribe" }).then((unsub) => { this._unsub = unsub; }).catch((err) => {
      this.error = (err && err.message) || "Abonnement mislukt";
      this._emit();
    });
    this.refreshSettings(hass);
  }

  refreshSettings(hass) {
    hass.connection.sendMessagePromise({ type: "hems/settings" }).then((s) => { this.settings = s; this._emit(); })
      .catch((err) => { this.settings = null; this.settingsError = (err && err.message) || "geen instellingen"; this._emit(); });
  }

  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  _emit() { for (const fn of this.listeners) fn(); }
}

const store = window.__hemsStore || (window.__hemsStore = new HemsStore());

/* ------------------------------------------------------------------ format */

let TZ;
const fmtCache = {};
function tzOf(hass) { return (hass && hass.config && hass.config.time_zone) || undefined; }
function fmt(key, opts) {
  const k = key + "|" + (TZ || "");
  if (!fmtCache[k]) fmtCache[k] = new Intl.DateTimeFormat("nl-NL", { timeZone: TZ, ...opts });
  return fmtCache[k];
}
const hhmm = (d) => d ? fmt("t", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(d)) : "—";
const dayShort = (d) => fmt("d", { weekday: "short", day: "numeric", month: "short" }).format(new Date(d));
const localHour = (d) => Number(fmt("h", { hour: "numeric", hourCycle: "h23" }).format(new Date(d)));
const localDayKey = (d) => fmt("k", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(d));
function num(v, dec = 1) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const x = Math.abs(Number(v)) < 0.5 * 10 ** -dec ? 0 : Number(v);
  return x.toLocaleString("nl-NL", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
const eur = (v, dec = 4) => v === null || v === undefined ? "—" : num(v, dec);
const kw = (w, dec = 1) => w === null || w === undefined ? "—" : num(Math.abs(Number(w)) < 50 ? 0 : Number(w) / 1000, dec);
function age(ms) {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return s + " s";
  const m = Math.round(s / 60);
  if (m < 90) return m + " min";
  const h = Math.round(m / 60);
  return h < 48 ? h + " u" : Math.round(h / 24) + " d";
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ACTION_NL = { charge: "Laden", discharge: "Ontladen", idle: "Rust" };
const EXEC_NL = {
  as_planned: "volgens plan", at_floor: "op de vloer", limited_floor: "begrensd door vloer", at_full: "batterij vol",
  limited_full: "begrensd: bijna vol", no_soc: "geen SoC", stale_soc: "SoC verouderd", expired: "plan verlopen", no_plan: "geen plan",
};
const STATUS_NL = {
  ok: "ok", no_soc: "geen SoC: HEMS plant niets", stale_soc: "SoC verouderd: HEMS plant niets", no_prices: "geen prijzen",
  no_price_for_now: "geen prijs voor dit kwartier",
};
const EV_NL = {
  off: "module uit", not_plugged: "niet ingeplugd", no_soc: "geen SoC van de auto", problem: "laadpaal meldt een probleem", idle: "niets te laden",
  planned: "gepland", deadline_at_risk: "deadline in gevaar", forced: "geforceerd laden",
};
const WINDOW_NL = { planned: "gepland", partial: "deels", no_stock: "geen voorraad", kept_for_later: "bewaard voor later", unsold: "niet verkocht" };
const HEAT_NL = { night: "nacht", heating: "verwarmen", legionella: "legionella" };
const DAY_NL = { monday: "maandag", tuesday: "dinsdag", wednesday: "woensdag", thursday: "donderdag", friday: "vrijdag", saturday: "zaterdag", sunday: "zondag" };
const TIER_NL = { deadline: "deadline", cheap: "goedkoop", forced: "geforceerd", surplus: "zon" };

/* ------------------------------------------------------------------ styles */

const TOKENS = `
:host {
  --bg:#eef0f2; --panel:#ffffff; --panel-2:#f5f6f8; --line:#d5d9de; --line-2:#e4e7eb;
  --fg:#1b2026; --fg-2:#4b5560; --fg-3:#6f7984;
  --charge:#2f6fd0; --charge-soft:rgba(47,111,208,.16);
  --discharge:#c0611a; --discharge-soft:rgba(201,102,26,.16);
  --pv:#9a7800; --pv-soft:rgba(214,170,20,.22);
  --load:#55606b; --load-soft:rgba(85,96,107,.16);
  --cheap:#2f6fd0; --dear:#c9661a; --mid:#c3c8ce;
  --ok:#2b8a57; --warn:#a87400; --fault:#c2362f; --stale:#7d62a6; --dry:#6b7480;
  --font-display:"Archivo Narrow","Roboto Condensed","Arial Narrow",system-ui,sans-serif;
  --font-body:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --font-data:ui-monospace,"SFMono-Regular","Roboto Mono",Menlo,Consolas,monospace;
}
:host([dark]) {
  --bg:#12161b; --panel:#1a1f26; --panel-2:#20262e; --line:#323a44; --line-2:#272e37;
  --fg:#e6e9ec; --fg-2:#a9b2bc; --fg-3:#8a95a2;
  --charge:#6ea2ef; --charge-soft:rgba(110,162,239,.20);
  --discharge:#f0a05a; --discharge-soft:rgba(240,160,90,.20);
  --pv:#e2bd3a; --pv-soft:rgba(226,189,58,.18);
  --load:#a3adb8; --load-soft:rgba(163,173,184,.14);
  --cheap:#6ea2ef; --dear:#f0a05a; --mid:#3a434e;
  --ok:#4fbf83; --warn:#e3b341; --fault:#f0675f; --stale:#b39ddb; --dry:#8b95a1;
  color-scheme: dark;
}`;

const BASE_CSS = `
${TOKENS}
:host { display:block; background:var(--bg); color:var(--fg); font:14px/1.45 var(--font-body); }
* { box-sizing:border-box; }
button { font:inherit; color:inherit; }
.mono, .num { font-family:var(--font-data); font-variant-numeric:tabular-nums; }
.eyebrow { font:600 11px/1.2 var(--font-data); letter-spacing:.1em; text-transform:uppercase; color:var(--fg-3); }
.tag { display:inline-flex; align-items:center; gap:6px; font:600 11px/1 var(--font-data); letter-spacing:.06em; padding:5px 7px; border-radius:3px; border:1px solid currentColor; white-space:nowrap; }
.tag.dry { color:var(--dry); border-style:dashed; }
.tag.off { color:var(--fg-3); border-color:var(--line); }
.tag.ok { color:var(--ok); }
.tag.warn { color:var(--warn); }
.tag.fault { color:var(--fault); }
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; flex:none; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:6px; min-width:0; }
.pad { padding:12px 14px; }
.stack { display:flex; flex-direction:column; gap:8px; }
.row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.kv { display:grid; grid-template-columns:auto 1fr; gap:3px 14px; font:12px/1.5 var(--font-data); }
.kv > :nth-child(odd) { color:var(--fg-3); }
.kv > :nth-child(even) { text-align:right; font-variant-numeric:tabular-nums; }
.muted { color:var(--fg-3); }
.small { font-size:12px; }
.empty { padding:24px 14px; text-align:center; color:var(--fg-3); font-size:13px; }
.stale-frame { outline:1px dashed var(--stale); outline-offset:-1px; }
.would { font:600 11px var(--font-data); letter-spacing:.08em; color:var(--dry); border:1px dashed var(--dry); padding:3px 6px; border-radius:3px; }
.verdict { display:flex; flex-direction:column; gap:8px; }
.verdict .big { font:700 32px/1.05 var(--font-display); letter-spacing:-.01em; }
.verdict .why { color:var(--fg-2); font-size:14px; max-width:70ch; }
.cmp { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px; }
.cmp > div { border:1px solid var(--line); border-radius:4px; padding:6px 8px; background:var(--panel-2); min-width:0; }
.cmp b { display:block; font:600 16px var(--font-data); font-variant-numeric:tabular-nums; }
.cmp small { font:10px var(--font-data); color:var(--fg-3); letter-spacing:.06em; text-transform:uppercase; }
.cmp .win { border-color:var(--fg); box-shadow:inset 0 0 0 1px var(--fg); }
.c-charge { color:var(--charge); } .c-discharge { color:var(--discharge); } .c-idle { color:var(--fg-2); }
.tiles { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px; }
.tile { border:1px solid var(--line); background:var(--panel); border-radius:5px; padding:8px; display:flex; flex-direction:column; gap:1px; min-width:0; }
.tile small { font:600 10px var(--font-data); letter-spacing:.1em; color:var(--fg-3); text-transform:uppercase; }
.tile b { font:600 19px var(--font-data); font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.tile i { font-style:normal; font:11px var(--font-data); color:var(--fg-3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.tile.stale { border-style:dashed; border-color:var(--stale); }
.tile.stale b { color:var(--fg-3); }
.tile.stale i { color:var(--stale); }
.chain { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); }
.chain > div { border:1px solid var(--line); background:var(--panel); padding:6px 8px; font:11px/1.35 var(--font-data); color:var(--fg-2); min-width:0; }
.chain > div + div { border-left:none; }
.chain b { display:block; font-size:12px; color:var(--fg); }
.chain .ovr { background:var(--discharge-soft); }
.bar { height:10px; background:var(--panel-2); border:1px solid var(--line); position:relative; border-radius:2px; overflow:hidden; }
.bar > i { position:absolute; top:0; bottom:0; left:0; }
.bar > em { position:absolute; top:-2px; bottom:-2px; width:2px; }
.btn { font:600 13px var(--font-body); padding:10px 14px; border-radius:4px; border:1px solid var(--line); background:var(--panel-2); color:var(--fg); min-height:44px; cursor:pointer; }
.btn.pri { background:var(--fg); color:var(--bg); border-color:var(--fg); }
.btn.danger { background:var(--fault); color:#fff; border-color:var(--fault); }
.btn[disabled] { opacity:.5; cursor:not-allowed; }
.seg { display:inline-flex; border:1px solid var(--line); border-radius:4px; overflow:hidden; }
.seg button { border:none; background:var(--panel); padding:7px 11px; font:600 11px var(--font-data); cursor:pointer; color:var(--fg-2); min-height:36px; }
.seg button[aria-pressed="true"] { background:var(--fg); color:var(--bg); }
table { border-collapse:collapse; width:100%; font-size:12px; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line-2); vertical-align:top; }
th { font:600 10px var(--font-data); letter-spacing:.08em; text-transform:uppercase; color:var(--fg-3); }
td.n { text-align:right; font-family:var(--font-data); font-variant-numeric:tabular-nums; }
.scroll-x { overflow-x:auto; }
svg text { font-family:var(--font-data); }
:focus-visible { outline:2px solid var(--charge); outline-offset:2px; }
@media (prefers-reduced-motion: no-preference) { .pulse { animation:pl 2s ease-in-out infinite; } @keyframes pl { 50% { opacity:.35; } } }
`;

/* ------------------------------------------------------------------ helpers on the payload */

function stateAge(hass, entityId) {
  const st = entityId && hass && hass.states[entityId];
  if (!st) return null;
  return Date.now() - new Date(st.last_updated).getTime();
}

function stateNum(hass, entityId) {
  const st = entityId && hass && hass.states[entityId];
  if (!st || st.state === "unavailable" || st.state === "unknown") return null;
  const v = Number(st.state);
  return Number.isFinite(v) ? v : null;
}

function planAgeMs(p) { return p && p.meta && p.meta.cycle_at ? Date.now() - new Date(p.meta.cycle_at).getTime() : null; }
function planStale(p) { const a = planAgeMs(p); return a !== null && a > p.meta.stale_after_s.plan * 1000; }

function priceStats(rows) {
  const today = rows.length ? localDayKey(rows[0].t) : null;
  const day = rows.filter((r) => localDayKey(r.t) === today).map((r) => r.imp);
  const all = rows.map((r) => r.imp);
  const avg = day.length ? day.reduce((a, b) => a + b, 0) / day.length : null;
  return { avg, min: all.length ? Math.min(...all) : null, max: all.length ? Math.max(...all) : null };
}

/* ------------------------------------------------------------------ timeline (SVG) */

const SVGNS = "http://www.w3.org/2000/svg";

function cssVar(el, name) { return getComputedStyle(el).getPropertyValue(name).trim(); }

/**
 * Draw the shared time axis into `svg`. opts: {hours, lanes:[...], selected, onSelect, compact}
 * Lanes: price, plan, soc, pvload, devices.
 */
function drawTimeline(host, svg, payload, opts) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const rows = (payload && payload.quarters) || [];
  const width = Math.max(320, Math.round(svg.getBoundingClientRect().width || svg.parentNode.clientWidth || 600));
  const font = opts.compact ? 10 : 11;
  const L = 44, R = 8;
  const n = Math.min(rows.length, Math.round(opts.hours * 4));
  const view = rows.slice(0, n);
  const C = (v) => cssVar(host, v);
  const el = (tag, attrs, parent = svg) => { const e = document.createElementNS(SVGNS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.appendChild(e); return e; };
  const txt = (t, x, y, a = {}) => { const e = el("text", { x, y, fill: C("--fg-3"), "font-size": font, ...a }); e.textContent = t; return e; };

  const laneH = { price: opts.compact ? 54 : 84, plan: opts.compact ? 40 : 54, soc: opts.compact ? 54 : 80, pvload: opts.compact ? 46 : 64, devices: 34 };
  const lanes = opts.lanes.filter((k) => k !== "devices" || view.some((r) => r.ev_a || r.heat));
  let H = 8; for (const k of lanes) H += laneH[k] + 12; H += 22;
  svg.setAttribute("viewBox", `0 0 ${width} ${H}`);
  svg.setAttribute("height", H);
  if (!n) {
    txt("Geen plan om te tonen", width / 2, H / 2, { "text-anchor": "middle", fill: C("--fg-2") });
    return;
  }
  const t0 = new Date(view[0].t).getTime();
  const span = n * Q_MS;
  const X = (ms) => L + (ms - t0) / span * (width - L - R);
  const qw = (width - L - R) / n;
  const dry = !payload.meta || payload.meta.dry_run !== false;

  const defs = el("defs", {});
  for (const k of ["charge", "discharge"]) {
    const p = el("pattern", { id: `h-${k}`, width: 5, height: 5, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
    el("rect", { width: 5, height: 5, fill: C(`--${k}-soft`) }, p);
    el("line", { x1: 0, y1: 0, x2: 0, y2: 5, stroke: C(`--${k}`), "stroke-width": 1.3, "stroke-opacity": .7 }, p);
  }

  const st = priceStats(rows);
  const priceColor = (p) => {
    if (st.avg === null) return [C("--mid"), .5];
    if (p < st.avg) return [C("--cheap"), .25 + .6 * Math.min(1, (st.avg - p) / Math.max(1e-6, st.avg - st.min))];
    return [C("--dear"), .25 + .6 * Math.min(1, (p - st.avg) / Math.max(1e-6, st.max - st.avg))];
  };

  let y = 8;
  const lanePos = {};
  for (const k of lanes) {
    const top = y, h = laneH[k], bot = top + h;
    lanePos[k] = { top, bot };
    el("rect", { x: L, y: top, width: width - L - R, height: h, fill: C("--panel"), stroke: C("--line") });
    if (k === "price") {
      const vmax = Math.max(0.05, Math.ceil((st.max ?? .4) * 20) / 20), vmin = Math.min(0, Math.floor((Math.min(...view.map((r) => r.exp))) * 20) / 20);
      const sy = (v) => bot - (v - vmin) / (vmax - vmin) * h;
      if (vmin < 0) el("line", { x1: L, x2: width - R, y1: sy(0), y2: sy(0), stroke: C("--line") });
      view.forEach((r, i) => { const [c, a] = priceColor(r.imp); el("rect", { x: L + i * qw, y: sy(r.imp), width: qw + .3, height: Math.max(0, sy(Math.max(0, vmin)) - sy(r.imp)), fill: c, "fill-opacity": a }); });
      let d = "", e = "";
      view.forEach((r, i) => { d += `${i ? "L" : "M"}${L + i * qw},${sy(r.imp)}H${L + (i + 1) * qw}`; e += `${i ? "L" : "M"}${L + i * qw},${sy(r.exp)}H${L + (i + 1) * qw}`; });
      el("path", { d, fill: "none", stroke: C("--fg-2"), "stroke-width": 1 });
      el("path", { d: e, fill: "none", stroke: C("--fg-3"), "stroke-width": 1, "stroke-dasharray": "2 2" });
      if (st.avg !== null) el("line", { x1: L, x2: width - R, y1: sy(st.avg), y2: sy(st.avg), stroke: C("--fg-3"), "stroke-dasharray": "4 3", "stroke-width": .8 });
      txt(num(vmax, 2), L - 4, top + font, { "text-anchor": "end" });
      txt("€/kWh", L - 4, bot, { "text-anchor": "end" });
      // the horizon ends where the known prices end: say so instead of drawing nothing
      const endMs = t0 + n * Q_MS, wantMs = t0 + opts.hours * 3600e3;
      if (wantMs - endMs > Q_MS) {
        const tm = payload.meta && payload.meta.tomorrow_quarters ? "" : " · morgen ±13:15";
        txt("prijzen nog onbekend" + tm, width - R - 6, top + h / 2, { "text-anchor": "end", fill: C("--fg-3") });
      }
    }
    if (k === "plan") {
      const mid = top + h / 2;
      el("line", { x1: L, x2: width - R, y1: mid, y2: mid, stroke: C("--line") });
      const maxW = (payload.battery && payload.battery.max_power_kw * 1000) || 8000;
      view.forEach((r, i) => {
        if (!r.w || !r.act || r.act === "idle") return;
        const kind = r.w > 0 ? "charge" : "discharge";
        const hh = Math.min(1, Math.abs(r.w) / maxW) * (h / 2 - 2);
        el("rect", { x: L + i * qw, y: r.w > 0 ? mid - hh : mid, width: qw + .3, height: hh, fill: dry ? `url(#h-${kind})` : C(`--${kind}`) });
      });
      // sell windows as brackets under the lane
      for (const w of payload.sell_windows || []) {
        const a = new Date(w.from).getTime(), b = new Date(w.to).getTime();
        if (b <= t0 || a >= t0 + span) continue;
        const xa = Math.max(L, X(a)), xb = Math.min(width - R, X(b));
        el("path", { d: `M${xa},${bot - 1}v-4M${xa},${bot - 1}H${xb}M${xb},${bot - 1}v-4`, stroke: C(w.status === "unsold" ? "--fault" : "--discharge"), fill: "none", "stroke-width": 1.2 });
      }
      txt("+" + num(maxW / 1000, 0) + " kW", L - 4, top + font, { "text-anchor": "end" });
      txt("−", L - 4, bot, { "text-anchor": "end" });
    }
    if (k === "soc") {
      const cap = (payload.battery && payload.battery.capacity_kwh) || 25;
      const sy = (v) => bot - v / cap * h;
      const b = payload.battery || {};
      [[b.reserve_kwh, "reserve", "--warn"], [b.floor_kwh, "vloer", "--fault"]].forEach(([v, label, c]) => {
        if (v === undefined || v === null) return;
        el("line", { x1: L, x2: width - R, y1: sy(v), y2: sy(v), stroke: C(c), "stroke-dasharray": "3 3", "stroke-width": .9 });
        txt(label, width - R - 4, sy(v) - 3, { "text-anchor": "end", fill: C(c) });
      });
      const prev = (payload.diff && payload.diff.previous_soc) || {};
      let g = "", started = false;
      view.forEach((r, i) => { const v = prev[r.t]; if (v === undefined) { started = false; return; } g += `${started ? "L" : "M"}${L + (i + .5) * qw},${sy(v)}`; started = true; });
      if (g) el("path", { d: g, fill: "none", stroke: C("--fg-3"), "stroke-width": 1.2, "stroke-dasharray": "5 3" });
      let d = ""; started = false;
      view.forEach((r, i) => { if (r.soc === null) { started = false; return; } d += `${started ? "L" : "M"}${L + (i + .5) * qw},${sy(r.soc)}`; started = true; });
      el("path", { d, fill: "none", stroke: C("--fg"), "stroke-width": 2 });
      txt(num(cap, 0), L - 4, top + font, { "text-anchor": "end" });
      txt("kWh", L - 4, bot, { "text-anchor": "end" });
    }
    if (k === "pvload") {
      const mx = Math.max(0.5, ...view.map((r) => Math.max(r.pv_hi || r.pv || 0, r.load_hi || r.load || 0))) * 4;   // kWh per quarter -> kW
      const sy = (v) => bot - v / mx * h;
      for (const [key, c] of [["pv", "--pv"], ["load", "--load"]]) {
        const up = [], dn = [];
        view.forEach((r, i) => { if (r[key + "_hi"] === null || r[key + "_hi"] === undefined) return; up.push(`${L + (i + .5) * qw},${sy(r[key + "_hi"] * 4)}`); dn.unshift(`${L + (i + .5) * qw},${sy(r[key + "_lo"] * 4)}`); });
        if (up.length > 1) el("path", { d: `M${up.join("L")}L${dn.join("L")}Z`, fill: C(c), "fill-opacity": .12, stroke: "none" });
        let area = "", line = "", started = false;
        const pts = [];
        view.forEach((r, i) => { if (r[key] === null) { started = false; return; } const v = r[key] * 4; pts.push([L + (i + .5) * qw, sy(v)]); line += `${started ? "L" : "M"}${L + (i + .5) * qw},${sy(v)}`; started = true; });
        if (pts.length) { area = `M${pts[0][0]},${bot}` + pts.map((p) => `L${p[0]},${p[1]}`).join("") + `L${pts[pts.length - 1][0]},${bot}Z`; el("path", { d: area, fill: C(c + "-soft") }); }
        el("path", { d: line, fill: "none", stroke: C(c), "stroke-width": 1.4 });
      }
      txt(num(mx, 1), L - 4, top + font, { "text-anchor": "end" });
      txt("kW", L - 4, bot, { "text-anchor": "end" });
    }
    if (k === "devices") {
      const rh = (h - 6) / 2;
      txt("auto", L - 4, top + rh, { "text-anchor": "end" });
      txt("boiler", L - 4, top + 2 * rh + 4, { "text-anchor": "end" });
      view.forEach((r, i) => {
        if (r.ev_a) el("rect", { x: L + i * qw, y: top + 3, width: qw + .3, height: rh - 2, fill: dry ? "url(#h-charge)" : C("--charge") });
        if (r.heat) el("rect", { x: L + i * qw, y: top + rh + 4, width: qw + .3, height: rh - 2, fill: dry ? "url(#h-discharge)" : C("--discharge") });
      });
    }
    const labels = { price: "prijs", plan: "plan", soc: "SoC", pvload: "zon/huis", devices: "" };
    if (labels[k]) {
      const lb = txt(labels[k], L + 5, top + font + 2, { fill: C("--fg-2"), "font-weight": 600, "paint-order": "stroke", stroke: C("--panel"), "stroke-width": 3 });
      lb.setAttribute("pointer-events", "none");
    }
    y = bot + 12;
  }

  // hour grid and labels
  const stepH = opts.hours > 30 ? 6 : opts.hours > 12 ? 3 : 1;
  view.forEach((r, i) => {
    const ms = new Date(r.t).getTime();
    const d = new Date(ms);
    if (d.getUTCMinutes() !== 0) return;
    const hr = localHour(ms);
    if (hr % stepH !== 0) return;
    const x = L + i * qw;
    el("line", { x1: x, x2: x, y1: 8, y2: y - 12, stroke: C(hr === 0 ? "--fg-3" : "--line-2"), "stroke-width": hr === 0 ? 1 : .6 });
    txt(String(hr).padStart(2, "0"), x, y + 2, { "text-anchor": "middle" });
    if (hr === 0) txt(dayShort(ms), x + 3, 8 + font, { fill: C("--fg-2") });
  });

  // now
  const nowX = X(Date.now());
  if (nowX >= L && nowX <= width - R) {
    el("line", { x1: nowX, x2: nowX, y1: 4, y2: y - 10, stroke: C("--fg"), "stroke-width": 1.6 });
  }

  // selection + hit area
  if (opts.selected !== null && opts.selected !== undefined && opts.selected < n) {
    el("rect", { x: L + opts.selected * qw, y: 6, width: Math.max(qw, 2), height: y - 16, fill: C("--fg"), "fill-opacity": .12, stroke: C("--fg"), "stroke-width": .8 });
  }
  const hit = el("rect", { x: L, y: 0, width: width - L - R, height: H, fill: "transparent", style: "cursor:crosshair" });
  const pick = (ev) => {
    const box = svg.getBoundingClientRect();
    const px = (ev.clientX - box.left) * (width / box.width);
    const i = Math.max(0, Math.min(n - 1, Math.floor((px - L) / qw)));
    if (opts.onSelect) opts.onSelect(i);
  };
  hit.addEventListener("click", pick);
  svg.setAttribute("tabindex", "0");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Plan voor ${opts.hours} uur: prijs, acties, SoC en verwachtingen. Pijltjes kiezen een kwartier.`);
  svg.onkeydown = (ev) => {
    if (!opts.onSelect) return;
    const cur = opts.selected ?? -1;
    if (ev.key === "ArrowRight") { opts.onSelect(Math.min(n - 1, cur + 1)); ev.preventDefault(); }
    if (ev.key === "ArrowLeft") { opts.onSelect(Math.max(0, cur - 1)); ev.preventDefault(); }
  };
}

/* ------------------------------------------------------------------ html fragments */

function healthHtml(p, store) {
  if (!p) return "";
  const m = p.meta;
  const stale = planStale(p);
  const statusOk = m.status === "ok";
  const tomorrow = m.tomorrow_quarters > 0;
  return `<span class="row small mono" style="gap:12px;color:var(--fg-2)">
    <span class="row" style="gap:5px"><i class="dot ${statusOk && !stale ? "pulse" : ""}" style="background:var(${stale ? "--stale" : statusOk ? "--ok" : "--fault"})"></i>
      ${stale ? "plan verouderd · " : ""}cyclus ${hhmm(m.cycle_at)} (${age(planAgeMs(p))})</span>
    <span class="row" style="gap:5px"><i class="dot" style="background:var(${m.price_source === "market" ? "--ok" : "--warn"})"></i>prijzen: ${m.price_source === "market" ? "Nord Pool" : esc(m.price_source || "—")}</span>
    <span class="row" style="gap:5px"><i class="dot" style="background:var(${tomorrow ? "--ok" : "--warn"})"></i>morgen: ${tomorrow ? "bekend" : "nog niet"}</span>
    <span class="row" style="gap:5px"><i class="dot" style="background:var(${m.weather_age_min !== null && m.weather_age_min < 90 ? "--ok" : "--warn"})"></i>weer ${m.weather_age_min === null ? "—" : num(m.weather_age_min, 0) + " min"}</span>
    <span>build ${esc(String(m.build || "?").slice(0, 7))}</span>
  </span>`;
}

const MODE_NL = { dry_run: "DRY-RUN", advisory: "ADVIES" };
function modeStripHtml(p, settings) {
  const o = (settings && settings.options) || {};
  const c = (p && p.control) || { modes: {}, armed: false };
  const tag = (label, enabled, mode) => enabled === false ? `<span class="tag off">${label} · UIT</span>`
    : mode === "advisory" ? `<span class="tag warn">${label} · ADVIES</span>` : `<span class="tag dry">${label} · DRY-RUN</span>`;
  const anyAdvice = Object.values(c.modes || {}).some((m) => m === "advisory");
  return `<span class="tag ${c.armed ? "fault" : "ok"}" title="Geen enkele module schrijft nog naar een apparaat">${c.armed ? "GEWAPEND · nog geen module stuurt" : "VEILIG · HEMS STUURT NIETS"}</span>
    ${tag("BATTERIJ", true, c.modes.battery)} ${tag("AUTO", o.ev_enabled, c.modes.ev)} ${tag("BOILER", o.water_heater_enabled, c.modes.water_heater)}
    ${c.armed || anyAdvice ? `<button class="btn danger" data-act="disarm" style="min-height:32px;padding:4px 10px">Alles naar dry-run</button>` : ""}`;
}

function alertsHtml(p) {
  const a = (p && p.alerts) || {};
  const label = { data: "Gegevens ontbreken", deadline: "Auto-deadline in gevaar", not_executed: "Plan niet uitgevoerd", legionella: "Legionella-run te laat" };
  const on = Object.entries(a).filter(([, v]) => v && v.on);
  if (!on.length) return "";
  return `<div class="alerts">${on.map(([k, v]) => `<div class="alert"><b>${label[k] || k}</b> <span>${esc(v.reason || "")}</span></div>`).join("")}</div>`;
}

function recText(r) {
  const x = r.payload || {};
  if (r.module === "battery") return `${ACTION_NL[x.action] || x.action} ${hhmm(x.from)}–${hhmm(x.to)} op ${kw(x.power_w)} kW (${num(x.kwh, 1)} kWh)`;
  if (r.module === "ev") return `Auto laden ${hhmm(x.from)}–${hhmm(x.to)} op ${num(x.current_a, 0)} A (${num(x.kwh, 1)} kWh, ${TIER_NL[x.tier] || x.tier})`;
  return `Boiler ${HEAT_NL[x.kind] || x.kind} ${hhmm(x.from)}–${hhmm(x.to)} (${num(x.kwh, 1)} kWh)`;
}

function recsHtml(p, confirmId) {
  const recs = (p && p.control && p.control.recommendations) || [];
  if (!recs.length) return "";
  return `<section class="stack"><span class="eyebrow">Advies</span>${recs.map((r) => `<div class="rec">
    <div class="row" style="justify-content:space-between"><b>${esc(recText(r))}</b>${r.status === "applied" ? `<span class="tag ok">TOEGEPAST ${hhmm(r.applied_at)}</span>` : ""}</div>
    ${r.reason ? `<div class="small muted">${esc(r.reason)}</div>` : ""}
    ${r.status === "applied" ? "" : confirmId === r.id
      ? `<div class="small">HEMS vuurt <span class="mono">hems_recommendation_applied</span> af; jouw automatisering voert het uit. Doorgaan?</div>
         <div class="row"><button class="btn pri" data-apply-yes="${esc(r.id)}">Ja, toepassen</button><button class="btn" data-apply-no>Annuleren</button></div>`
      : `<div class="row"><button class="btn pri" data-apply="${esc(r.id)}">Toepassen</button><button class="btn" data-dismiss="${esc(r.id)}">Negeren</button></div>`}
  </div>`).join("")}</section>`;
}

function verdictHtml(p, big = 32) {
  if (!p) return `<div class="empty">Wachten op de eerste HEMS-cyclus…</div>`;
  const d = p.decision;
  if (!d) {
    return `<div class="verdict"><span class="eyebrow">HEMS plant nu niets</span>
      <span class="big" style="font-size:${big}px;color:var(--fault)">${esc(STATUS_NL[p.meta.status] || p.meta.status)}</span>
      <span class="why">Zodra de ontbrekende gegevens er zijn, plant HEMS binnen een minuut opnieuw. Prijzen en verwachtingen blijven zichtbaar.</span></div>`;
  }
  const e = p.execution;
  const act = d.action || "idle";
  const w = e && e.code !== "no_plan" ? e.power_w : d.power_w;
  const c = d.compare || {};
  const best = c.code === "sell" ? "sell" : c.code === "buy" ? "buy" : c.code === "hold" ? "keep" : null;
  const tile = (k, label, v, extra = "") => `<div class="${best === k ? "win" : ""}"><small>${label}</small><b>${eur(v)}</b>${extra}</div>`;
  const later = c.best_sell_later ? `<small>beste later ${hhmm(c.best_sell_later.at)} · ${eur(c.best_sell_later.value)}</small>` : "";
  return `<div class="verdict">
    <div class="row" style="align-items:baseline;gap:10px">
      <span class="would" title="Dry-run: dit zou HEMS doen, er wordt niets verzonden">ZOU</span>
      <span class="big c-${act}" style="font-size:${big}px">${ACTION_NL[act] || act}${act !== "idle" ? " " + kw(Math.abs(w)) + " kW" : ""}</span>
    </div>
    <div class="why">${esc(d.reason || "")}</div>
    <div class="cmp">${tile("sell", "verkoop nu", c.sell)}${tile("keep", "bewaar", c.keep, later)}${tile("buy", "koop nu", c.buy)}</div>
    <div class="small muted mono">€ per opgeslagen kWh · import ${eur(d.import_price)} · export ${eur(d.export_price)} · SoC ${num(d.soc_pct, 0)} %</div>
  </div>`;
}

function chainHtml(p) {
  if (!p || !p.decision) return "";
  const e = p.execution;
  return `<div class="chain" aria-label="Beslisketen">
    <div><b>Voorstel</b>${kw(p.decision.power_w)} kW</div>
    <div><b>Engine</b>${kw(e.planned_w)} kW</div>
    <div class="${e.overridden ? "ovr" : ""}" title="${esc(e.reason || "")}"><b>Executor</b>${kw(e.power_w)} kW · ${esc(EXEC_NL[e.code] || e.code)}</div>
    <div><b>Verzonden</b>— dry-run</div>
  </div>${e.overridden ? `<div class="small" style="color:var(--discharge);margin-top:4px">Executor wijkt af: ${esc(e.reason)}</div>` : ""}`;
}

function liveTilesHtml(hass, p, settings) {
  const r = (settings && settings.roles) || {};
  const limit = ((p && p.meta.stale_after_s.live) || 120) * 1000;
  const socLimit = ((p && p.meta.stale_after_s.soc) || 900) * 1000;
  const tile = (label, entity, valueFn, sub, lim = limit) => {
    if (!entity) return `<div class="tile"><small>${label}</small><b class="muted">—</b><i>geen entiteit</i></div>`;
    const a = stateAge(hass, entity);
    const v = stateNum(hass, entity);
    const stale = a === null || a > lim || v === null;
    return `<div class="tile ${stale ? "stale" : ""}" title="${esc(entity)}"><small>${label}</small><b>${v === null ? "—" : valueFn(v)}</b><i>${stale ? (v === null ? "geen waarde" : "verouderd " + age(a)) : sub(v) + " · " + age(a)}</i></div>`;
  };
  const pvIds = [r.pv_entity, ...(r.pv_extra_entities || [])].filter(Boolean);
  const pv = pvIds.length ? pvIds.map((id) => stateNum(hass, id)).reduce((a, b) => (a === null || b === null) ? null : a + b, 0) : null;
  const pvAge = pvIds.length ? Math.max(...pvIds.map((id) => stateAge(hass, id) ?? Infinity)) : null;
  const pvStale = pv === null || pvAge > limit;
  const battSign = r.battery_power_positive_is_discharging === false ? 1 : -1;     // contract: + charging
  const dec = p && p.decision;
  const imp = dec ? dec.import_price : null, exp = dec ? dec.export_price : null;
  return `<div class="tiles">
    <div class="tile ${pvStale ? "stale" : ""}"><small>Zon</small><b>${pv === null ? "—" : kw(pv)} kW</b><i>${pvStale ? "verouderd " + age(pvAge) : "nu · " + age(pvAge)}</i></div>
    ${tile("Net", r.grid_entity, (v) => `<span class="${v < 0 ? "c-charge" : ""}">${kw(v)}</span> kW`, (v) => v < 0 ? `export ${eur(exp)}` : `import ${eur(imp)}`)}
    ${tile("Batterij", r.battery_power_entity, (v) => { const x = v * battSign; return `<span class="${x > 0 ? "c-charge" : x < 0 ? "c-discharge" : ""}">${kw(x)}</span> kW`; }, (v) => { const x = v * battSign; return x > 0 ? "laden" : x < 0 ? "ontladen" : "rust"; })}
    ${tile("SoC", r.soc_entity, (v) => `${num(v, 0)} %`, (v) => `${num(v / 100 * ((p && p.battery.capacity_kwh) || 25), 1)} kWh`, socLimit)}
    ${tile("Auto", r.ev_power_entity, (v) => `${kw(v)} kW`, () => (p && p.ev ? EV_NL[p.ev.status] || p.ev.status : "laadpaal"))}
    ${tile("Auto SoC", r.ev_soc_entity, (v) => `${num(v, 0)} %`, () => "auto", 6 * 3600e3)}
  </div>`;
}

function whyHtml(p, i) {
  const rows = (p && p.quarters) || [];
  const r = rows[i];
  if (!r) return `<div class="empty">Tik op een kwartier in de tijdlijn voor het waarom.</div>`;
  const prev = p.diff && p.diff.previous_soc ? p.diff.previous_soc[r.t] : undefined;
  const changed = (p.diff && p.diff.runs || []).find((x) => x.from <= r.t && r.t < x.to);
  const cap = p.battery.capacity_kwh;
  const end = new Date(new Date(r.t).getTime() + Q_MS);
  return `<div class="stack">
    <span class="eyebrow">${dayShort(r.t)} · ${hhmm(r.t)}–${hhmm(end)}</span>
    <div class="row" style="align-items:baseline"><b class="c-${r.act || "idle"}" style="font:700 22px var(--font-display)">${r.act ? (ACTION_NL[r.act] || r.act) : "Niet gepland"}${r.w ? " " + kw(Math.abs(r.w)) + " kW" : ""}</b>
      ${r.act ? `<span class="would">ZOU</span>` : ""}</div>
    ${r.why ? `<div class="small" style="color:var(--fg-2)">${esc(r.why)}</div>` : ""}
    <div class="kv">
      <span>Import / export</span><span>${eur(r.imp)} / ${eur(r.exp)} €/kWh</span>
      <span>Verkoop · bewaar · koop</span><span>${eur(r.sell)} · ${eur(r.keep)} · ${eur(r.buy)}</span>
      <span>SoC na kwartier</span><span>${r.soc === null ? "—" : num(r.soc, 1) + " kWh (" + num(r.soc / cap * 100, 0) + " %)"}</span>
      ${prev !== undefined ? `<span>Vorig plan</span><span>${num(prev, 1)} kWh</span>` : ""}
      <span>Zon / huis (verwacht)</span><span>${num((r.pv ?? 0) * 4, 2)} / ${num((r.load ?? 0) * 4, 2)} kW</span>
      ${r.ev_a ? `<span>Auto</span><span>${num(r.ev_a, 0)} A · ${esc(TIER_NL[r.ev_tier] || r.ev_tier || "")}</span>` : ""}
      ${r.heat ? `<span>Boiler</span><span>${esc(HEAT_NL[r.heat] || r.heat)}</span>` : ""}
    </div>
    ${changed ? `<div class="small" style="color:var(--warn)">Gewijzigd t.o.v. vorig plan: was ${esc(ACTION_NL[changed.was] || changed.was)}, nu ${esc(ACTION_NL[changed.now] || changed.now)}.</div>` : ""}
    <div class="small muted">Verwachtingen zijn schattingen; de zon- en huisverwachting kan per kwartier flink afwijken.</div>
  </div>`;
}

function diffHtml(p) {
  const d = p && p.diff;
  if (!d || !d.available) return `<div class="small muted">Nog geen vorig plan om mee te vergelijken (eerste cyclus na een herstart).</div>`;
  if (!d.runs.length) return `<div class="small muted">Geen acties gewijzigd sinds het plan van ${hhmm(d.previous_at)}.</div>`;
  return `<div class="stack small">${d.runs.slice(0, 6).map((x) => `<div><b class="mono">${hhmm(x.from)}–${hhmm(x.to)}</b> ${esc(ACTION_NL[x.was] || x.was)} → <b class="c-${x.now}">${esc(ACTION_NL[x.now] || x.now)}</b>
    ${x.reason ? `<div class="muted">${esc(x.reason)}</div>` : ""}</div>`).join("")}
    ${d.runs.length > 6 ? `<div class="muted">… en ${d.runs.length - 6} meer</div>` : ""}</div>`;
}

function moneyHtml(p) {
  const d = p && p.decision;
  const r = p && p.realised;
  const t = r && r.today;
  const signed = (v) => v === null || v === undefined ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + "€ " + num(Math.abs(v), 2);
  return `<div class="kv">
    <span>Verwacht (horizon)</span><span>${d ? "€ " + num(d.expected_saving, 2) : "—"}</span>
    <span>Netto kosten vandaag</span><span>${t ? "€ " + num(t.cost, 2) : "—"}</span>
    <span>Zelfverbruik zou kosten</span><span>${t ? "€ " + num(t.baseline_cost, 2) : "—"}</span>
    <span>Verschil vandaag</span><span style="color:var(${t && t.gain >= 0 ? "--ok" : "--fault"})">${t ? signed(t.gain) : "—"}</span>
    <span>Totaal${r && r.since ? " sinds " + dayShort(r.since) : ""}</span><span>${r ? signed(r.gain_total) : "—"}</span>
  </div><div class="small muted" style="margin-top:6px">Gemeten aan de meter, per kwartier geprijsd; de baseline is de batterij op alleen zelfverbruik met dezelfde zon en hetzelfde huis.${t ? ` ${t.quarters} kwartieren vandaag.` : ""}</div>`;
}

function phasesHtml(hass, settings) {
  const r = (settings && settings.roles) || {};
  const o = (settings && settings.options) || {};
  const lim = Number(o.grid_limit_a || 25), margin = Number(o.grid_margin_a || 1);
  const ids = ["meter_current_l1_entity", "meter_current_l2_entity", "meter_current_l3_entity"].map((k) => r[k]);
  if (!ids.some(Boolean)) return `<div class="small muted">Geen fasestroom-entiteiten toegewezen (Instellingen → rollen).</div>`;
  return `<div class="stack">${ids.map((id, i) => {
    const v = stateNum(hass, id), a = stateAge(hass, id);
    const stale = v === null || a > 30000;
    const pct = v === null ? 0 : Math.min(100, Math.abs(v) / lim * 100);
    const color = v !== null && Math.abs(v) > lim - margin ? "--fault" : v !== null && Math.abs(v) > (lim - margin) * .8 ? "--warn" : "--load";
    return `<div class="row mono small" style="display:grid;grid-template-columns:24px 1fr 76px;gap:8px" title="${esc(id || "")}">
      <b>L${i + 1}</b><div class="bar ${stale ? "stale-frame" : ""}"><i style="width:${pct}%;background:var(${color})"></i><em style="left:${(lim - margin) / lim * 100}%;background:var(--fault)"></em></div>
      <span style="text-align:right">${v === null ? "—" : num(v, 1) + " A"}${stale && v !== null ? " ⧗" : ""}</span></div>`;
  }).join("")}<div class="small muted mono">grens ${num(lim, 0)} A − marge ${num(margin, 0)} A per fase</div></div>`;
}

/** A property set before the element was defined hides the class setter; move it through the setter. */
function upgradeProperty(el, prop) {
  if (Object.prototype.hasOwnProperty.call(el, prop)) { const v = el[prop]; delete el[prop]; el[prop] = v; }
}

/* ------------------------------------------------------------------ the panel */

const VIEWS = [
  ["nu", "Nu"], ["plan", "Plan"], ["prijzen", "Prijzen"], ["batterij", "Batterij"], ["auto", "Auto"], ["boiler", "Boiler"], ["net", "Net"], ["leren", "Leren"], ["regie", "Regie"],
];

class HemsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = (location.hash || "#nu").slice(1);
    if (!VIEWS.some((v) => v[0] === this._view)) this._view = "nu";
    this._hours = 24;
    this._sel = null;
    this._confirm = false;
    const q = new URLSearchParams(location.search);
    this._kiosk = q.has("kiosk");
    this._forceTheme = q.get("theme") || (this._kiosk ? "dark" : null);
    this._onHash = () => { const v = (location.hash || "#nu").slice(1); if (VIEWS.some((x) => x[0] === v)) { this._view = v; this._render(); } };
    this._onResize = () => this._drawCharts();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    TZ = tzOf(hass);
    store.attach(hass);
    const dark = this._forceTheme ? this._forceTheme === "dark" : !!(hass.themes && hass.themes.darkMode);
    this.toggleAttribute("dark", dark);
    if (first) this._render();
    else this._liveUpdate();
  }
  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }
  set route(v) { this._route = v; }

  connectedCallback() {
    for (const prop of ["narrow", "panel", "route", "hass"]) upgradeProperty(this, prop);
    this._off = store.on(() => this._render());
    window.addEventListener("hashchange", this._onHash);
    window.addEventListener("resize", this._onResize);
    this._tick = setInterval(() => this._liveUpdate(), 15000);
    this._ro = new ResizeObserver(() => {
      const wide = this._isWide();
      if (wide !== this._wide) this._render(); else this._drawCharts();
    });
    this._ro.observe(this);
  }
  disconnectedCallback() {
    if (this._off) this._off();
    window.removeEventListener("hashchange", this._onHash);
    window.removeEventListener("resize", this._onResize);
    clearInterval(this._tick);
    if (this._ro) this._ro.disconnect();
  }

  _isWide() { return this.clientWidth >= (this._kiosk ? 800 : 900); }

  _go(view) { if (location.hash !== "#" + view) history.replaceState(null, "", "#" + view); this._view = view; this._sel = null; this._render(); }

  _liveUpdate() {
    // live tiles and phase bars refresh with every state change; the rest only with a new payload
    const root = this.shadowRoot;
    if (!root || !this._hass) return;
    const p = store.payload, s = store.settings;
    const t = root.getElementById("live"); if (t) t.innerHTML = liveTilesHtml(this._hass, p, s);
    const ph = root.getElementById("phases"); if (ph) ph.innerHTML = phasesHtml(this._hass, s);
    const h = root.getElementById("health"); if (h) h.innerHTML = healthHtml(p, store);
  }

  _render() {
    if (!this._hass) return;
    if (this._armTimer) { clearTimeout(this._armTimer); this._armTimer = null; }      // a re-render ends a hold in progress
    const p = store.payload, s = store.settings;
    const wide = this._isWide();
    this._wide = wide;
    const header = this._kiosk ? "" : `<header class="top">
        <ha-menu-button></ha-menu-button>
        <span class="title">HEMS</span>
        <nav class="tabs" role="tablist">${VIEWS.map(([k, label]) => `<button role="tab" data-view="${k}" aria-selected="${this._view === k}">${label}</button>`).join("")}</nav>
      </header>`;
    let body;
    if (store.error) body = `<div class="panel pad" style="border-color:var(--fault)"><b style="color:var(--fault)">Geen verbinding met HEMS</b><div class="small">${esc(store.error)}</div></div>`;
    else if (store.loaded === false) body = `<div class="panel pad"><b>HEMS is niet geladen</b><div class="small muted">De integratie staat uit of start nog. Kijk bij Instellingen → Apparaten &amp; diensten → HEMS.</div></div>`;
    else body = this[`_view_${this._view}`](p, s, wide);
    this.shadowRoot.innerHTML = `<style>${BASE_CSS}${PANEL_CSS}</style>
      ${header}
      <div class="strip">${modeStripHtml(p, s)}<span class="sp"></span><span id="health">${healthHtml(p, store)}</span></div>
      ${alertsHtml(p)}
      <main class="${this._kiosk ? "kiosk" : ""}">${body}</main>
      ${this._kiosk ? `<nav class="ktabs">${VIEWS.slice(0, 4).map(([k, label]) => `<button data-view="${k}" aria-pressed="${this._view === k}">${label}</button>`).join("")}</nav>` : ""}`;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) { menu.hass = this._hass; menu.narrow = this._narrow; }
    this.shadowRoot.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => this._go(b.dataset.view)));
    this.shadowRoot.querySelectorAll("[data-hours]").forEach((b) => b.addEventListener("click", () => { this._hours = Number(b.dataset.hours); this._sel = null; this._render(); }));
    this._bindActions();
    this._drawCharts();
  }

  _drawCharts() {
    if (!this.shadowRoot || !store.payload) return;
    const hm = this.shadowRoot.getElementById("heat");
    if (hm) drawHeatmap(this, hm, store.payload);
    const dz = this.shadowRoot.getElementById("days");
    if (dz) drawDays(this, dz, store.payload);
    const svg = this.shadowRoot.getElementById("tl");
    if (!svg) return;
    const lanes = this._view === "nu" && this.clientWidth < 600 ? ["price", "plan", "soc"] : ["price", "plan", "soc", "pvload", "devices"];
    drawTimeline(this, svg, store.payload, {
      hours: this._hours, lanes, compact: this.clientWidth < 600, selected: this._sel,
      onSelect: (i) => {
        this._sel = i;
        const why = this.shadowRoot.getElementById("why");
        if (why) why.innerHTML = whyHtml(store.payload, i);
        this._drawCharts();
      },
    });
    if (this._sel !== null && document.activeElement === this) svg.focus();
  }

  _timelineBlock(p, opts = {}) {
    const stale = p && planStale(p);
    return `<section class="panel ${stale ? "stale-frame" : ""}">
      <div class="row pad" style="justify-content:space-between;padding-bottom:4px">
        <span class="eyebrow">${stale ? `Plan van ${hhmm(p.meta.cycle_at)} · verouderd` : "Tijdlijn · nu → " + this._hours + " uur"}</span>
        <span class="seg">${[8, 24, 48].map((h) => `<button data-hours="${h}" aria-pressed="${this._hours === h}">${h} u</button>`).join("")}</span>
      </div>
      <div style="padding:0 6px 6px"><svg id="tl" style="display:block;width:100%"></svg></div>
      <div class="legend small mono">
        <span><i style="background:var(--charge-soft);outline:1px dashed var(--charge)"></i>laden (dry-run)</span>
        <span><i style="background:var(--discharge-soft);outline:1px dashed var(--discharge)"></i>ontladen (dry-run)</span>
        <span><i style="background:var(--fg);height:2px"></i>SoC</span>
        <span><i style="border-top:2px dashed var(--fg-3);height:0;background:none"></i>vorig plan</span>
        <span><i style="background:var(--pv-soft);outline:1px solid var(--pv)"></i>zon</span>
        <span><i style="background:var(--load-soft);outline:1px solid var(--load)"></i>huis</span>
      </div>
      ${opts.why === false ? "" : `<div class="pad" id="why" style="border-top:1px solid var(--line)">${whyHtml(p, this._sel)}</div>`}
    </section>`;
  }

  _view_nu(p, s, wide) {
    const left = `<section class="panel pad">${verdictHtml(p, this._kiosk ? 44 : 32)}</section>
      ${recsHtml(p, this._applyId)}
      <section class="stack"><span class="eyebrow">Live</span><div id="live">${liveTilesHtml(this._hass, p, s)}</div></section>
      <section class="stack"><span class="eyebrow">Beslisketen batterij</span>${chainHtml(p)}</section>`;
    if (!wide) return `<div class="stack" style="gap:14px">${left}${this._timelineBlock(p)}</div>`;
    return `<div class="grid-nu">
      <div class="stack" style="gap:14px">${left}</div>
      <div class="stack" style="gap:14px">${this._timelineBlock(p)}
        <div class="grid2">
          <section class="panel pad stack"><span class="eyebrow">Plan gewijzigd</span>${diffHtml(p)}</section>
          <section class="panel pad stack"><span class="eyebrow">Geld</span>${moneyHtml(p)}</section>
        </div></div></div>`;
  }

  _view_plan(p) {
    return `<div class="stack" style="gap:14px">
      ${p && p.decision ? `<section class="panel pad"><span class="eyebrow">Plan in woorden</span><div style="font:600 16px var(--font-body);margin-top:4px">${esc(p.decision.plan_text || "—")}</div></section>` : ""}
      ${this._timelineBlock(p)}
      <div class="grid2">
        <section class="panel pad stack"><span class="eyebrow">Plan gewijzigd</span>${diffHtml(p)}</section>
        <section class="panel pad stack"><span class="eyebrow">Geld</span>${moneyHtml(p)}</section>
      </div>
      <section class="panel"><div class="pad"><span class="eyebrow">Vensters</span></div><div class="scroll-x">${windowsTable(p)}</div></section>
    </div>`;
  }

  _view_prijzen(p) {
    if (!p || !p.quarters.length) return `<div class="empty">Geen prijzen bekend.</div>`;
    const st = priceStats(p.quarters);
    const cheap = cheapestBlock(p.quarters, 12);
    const sells = (p.sell_windows || []).slice(0, 6);
    const netting = p.quarters.length ? p.quarters.reduce((a, r) => a + (r.imp - r.exp), 0) / p.quarters.length : null;
    return `<div class="stack" style="gap:14px">
      <div class="grid4">
        <div class="tile"><small>Gemiddeld vandaag</small><b>${eur(st.avg)}</b><i>€/kWh import</i></div>
        <div class="tile"><small>Laagste (horizon)</small><b class="c-charge">${eur(st.min)}</b><i>€/kWh</i></div>
        <div class="tile"><small>Hoogste (horizon)</small><b class="c-discharge">${eur(st.max)}</b><i>€/kWh</i></div>
        <div class="tile"><small>Import − export</small><b>${eur(netting)}</b><i>gem. verschil €/kWh</i></div>
      </div>
      <section class="panel"><div class="pad row" style="justify-content:space-between"><span class="eyebrow">Prijzen per kwartier (import)</span>
        <span class="small muted mono">${p.meta.tomorrow_quarters ? "morgen gepubliceerd" : "morgen verschijnt ±13:15"}</span></div>
        <div class="scroll-x" style="padding:0 6px 10px"><svg id="heat" style="display:block;min-width:620px;width:100%"></svg></div></section>
      <div class="grid2">
        <section class="panel pad stack"><span class="eyebrow">Goedkoopste blok van 3 uur</span>
          ${cheap ? `<div style="font:700 22px var(--font-display)" class="c-charge">${hhmm(cheap.from)}–${hhmm(cheap.to)}</div><div class="small mono">gemiddeld ${eur(cheap.avg)} €/kWh · ${dayShort(cheap.from)}</div>` : `<div class="small muted">Te weinig prijzen bekend.</div>`}</section>
        <section class="panel pad stack"><span class="eyebrow">Verkoopvensters</span>
          ${sells.length ? sells.map((w) => `<div class="row small mono" style="justify-content:space-between"><span>${hhmm(w.from)}–${hhmm(w.to)} · piek ${eur(w.peak)}</span><span class="tag ${w.status === "unsold" ? "fault" : w.status === "planned" ? "ok" : "off"}">${esc(WINDOW_NL[w.status] || w.status)}</span></div>`).join("") : `<div class="small muted">Geen verkoopvensters in de horizon.</div>`}</section>
      </div>
      <div class="small muted">Saldering eindigt op ${esc((store.settings && store.settings.options && store.settings.options.salderen_until) || "2027-01-01")}; HEMS rekent de exportprijs per datum al zonder energiebelasting-teruggave vanaf die dag.</div>
    </div>`;
  }

  _view_batterij(p, s) {
    if (!p) return `<div class="empty">Wachten op data…</div>`;
    const b = p.battery;
    const soc = stateNum(this._hass, s && s.roles && s.roles.soc_entity);
    const kwh = soc === null ? null : soc / 100 * b.capacity_kwh;
    const idleWhy = p.decision && p.decision.action === "idle" ? `<section class="panel pad stack"><span class="eyebrow">Waarom gebeurt er niets?</span><div>${esc(p.decision.reason || "")}</div></section>` : "";
    return `<div class="stack" style="gap:14px">
      <section class="panel pad stack"><span class="eyebrow">Voorraad</span>
        <div class="row" style="align-items:baseline;gap:14px"><b style="font:700 40px var(--font-display)">${soc === null ? "—" : num(soc, 0) + " %"}</b><span class="mono">${kwh === null ? "" : num(kwh, 1) + " kWh van " + num(b.capacity_kwh, 0)}</span></div>
        <div class="bar" style="height:16px"><i style="width:${soc ?? 0}%;background:var(--fg-2)"></i><em style="left:${b.reserve_kwh / b.capacity_kwh * 100}%;background:var(--warn)"></em><em style="left:${b.floor_kwh / b.capacity_kwh * 100}%;background:var(--fault)"></em></div>
        <div class="small mono muted">reserve ${num(b.reserve_kwh, 1)} kWh · vloer ${num(b.floor_kwh, 1)} kWh · max ${num(b.max_power_kw, 1)} kW · rendement ${num(b.round_trip_eff, 2)} · marge € ${num(b.min_profit_margin, 2)}/kWh</div>
      </section>
      ${idleWhy}
      <section class="panel pad">${verdictHtml(p)}<div style="margin-top:10px">${chainHtml(p)}</div></section>
      ${this._timelineBlock(p)}
      <section class="panel"><div class="pad"><span class="eyebrow">Verkoopvensters</span></div><div class="scroll-x">${sellTable(p)}</div></section>
    </div>`;
  }

  _view_auto(p, s) {
    const ev = p && p.ev;
    const on = s && s.options && s.options.ev_enabled;
    if (!on) return `<section class="panel pad stack"><span class="eyebrow">Auto</span><div>De EV-module staat uit.</div>${configureLink(s)}</section>`;
    if (!ev) return `<div class="empty">Nog geen EV-plan.</div>`;
    const quarters = (p.quarters || []).filter((r) => r.ev_a);
    const risk = ev.status === "deadline_at_risk";
    const sp = ev.setpoint;
    const forceOn = this._hass.states["switch.hems_ev_force_charge"] && this._hass.states["switch.hems_ev_force_charge"].state === "on";
    const days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
    const dnl = ["ma", "di", "wo", "do", "vr", "za", "zo"];
    return `<div class="stack" style="gap:14px">
      <section class="panel pad stack" style="${risk ? "border-color:var(--fault);box-shadow:inset 3px 0 0 var(--fault)" : ""}">
        <span class="eyebrow">Status</span>
        <div style="font:700 26px var(--font-display)" class="${risk ? "" : ""}">${esc(EV_NL[ev.status] || ev.status)}</div>
        <div class="small" style="color:var(--fg-2)">${esc(ev.reason || "")}</div>
        <div class="kv">
          <span>Deadline</span><span>${ev.deadline ? dayShort(ev.deadline) + " " + hhmm(ev.deadline) : "geen"}</span>
          <span>Nodig / extra / gepland</span><span>${num(ev.required_kwh, 1)} / ${num(ev.optional_kwh, 1)} / ${num(ev.planned_kwh, 1)} kWh</span>
          ${ev.shortfall_kwh > 0 ? `<span style="color:var(--fault)">Tekort</span><span style="color:var(--fault)">${num(ev.shortfall_kwh, 1)} kWh</span>` : ""}
          <span>Setpoint (zou sturen)</span><span>${sp ? num(sp.current_a, 0) + " A · " + esc(sp.code) : "—"}</span>
          <span>Ruimte op het net</span><span>${ev.allowed_a === null || ev.allowed_a === undefined ? "onbekend" : num(ev.allowed_a, 1) + " A per fase"}</span>
        </div>
        ${sp && sp.reason && sp.reason !== ev.reason ? `<div class="small muted">${esc(sp.reason)}</div>` : ""}
      </section>
      <section class="panel pad stack"><span class="eyebrow">Geforceerd laden</span>
        <div class="small">Plant de benodigde energie zo vroeg en hard mogelijk, ongeacht de prijs. Stopt vanzelf als de auto vertrekt of het doel bereikt is, en staat na een herstart altijd uit.</div>
        ${this._confirm ? `<div class="row"><span class="small">${forceOn ? "Geforceerd laden stoppen?" : "Geforceerd laden starten? (dry-run: alleen het plan verandert)"}</span>
            <button class="btn pri" data-act="force-yes">${forceOn ? "Stoppen" : "Starten"}</button><button class="btn" data-act="force-no">Annuleren</button></div>`
          : `<div class="row"><span class="tag ${forceOn ? "warn" : "off"}">${forceOn ? "AAN" : "UIT"}</span><button class="btn" data-act="force">${forceOn ? "Stoppen…" : "Starten…"}</button></div>`}
      </section>
      ${this._timelineBlock(p, { why: false })}
      <section class="panel"><div class="pad"><span class="eyebrow">Geplande laadkwartieren</span></div><div class="scroll-x">
        ${quarters.length ? `<table><tr><th>Blok</th><th>Stroom</th><th>Laag</th><th>Gem. prijs</th><th>Zon</th></tr>${evBlocks(quarters).map((b) => `<tr><td class="mono">${dayShort(b.from)} ${hhmm(b.from)}–${hhmm(b.to)}</td><td class="n">${num(b.a, 0)} A</td><td>${esc(TIER_NL[b.tier] || b.tier)}</td><td class="n">${eur(b.price)}</td><td class="n">${num(b.pv, 1)} kWh</td></tr>`).join("")}</table>` : `<div class="empty">Geen laadkwartieren gepland.</div>`}
      </div></section>
      <section class="panel pad stack"><span class="eyebrow">Weekschema deadlines</span>
        <div class="row">${days.map((d, i) => { const t = s.options["ev_deadline_" + d]; return `<span class="tag ${t ? "ok" : "off"}">${dnl[i]} ${t || "—"}</span>`; }).join("")}</div>
        <div class="small muted">Doel ${num(s.options.ev_target_required_pct, 0)} % bij elke deadline, tot ${num(s.options.ev_target_max_pct, 0)} % onder € ${num(s.options.ev_max_price, 2)}/kWh.</div>${configureLink(s)}</section>
    </div>`;
  }

  _view_boiler(p, s) {
    const on = s && s.options && s.options.water_heater_enabled;
    if (!on) return `<section class="panel pad stack"><span class="eyebrow">Boiler</span><div>De boilermodule staat uit.</div>${configureLink(s)}</section>`;
    const runs = (p && p.heating) || [];
    const o = s.options;
    const wh = s.roles && s.roles.water_heater_entity && this._hass.states[s.roles.water_heater_entity];
    const temp = wh ? (wh.attributes.current_temperature ?? (Number.isFinite(Number(wh.state)) ? Number(wh.state) : null)) : null;
    const leg = p && p.alerts && p.alerts.legionella;
    const legDays = leg && leg.last ? (Date.now() - new Date(leg.last).getTime()) / 864e5 : null;
    return `<div class="stack" style="gap:14px">
      <div class="grid4">
        <div class="tile ${wh ? "" : "stale"}"><small>Tank</small><b>${temp === null ? "—" : num(temp, 0) + " °C"}</b><i>${wh ? esc(wh.state) + " · " + age(Date.now() - new Date(wh.last_updated).getTime()) : "geen entiteit toegewezen"}</i></div>
        <div class="tile ${leg && leg.on ? "stale" : ""}"><small>Legionella</small><b>${legDays === null ? "—" : num(legDays, 0) + " d geleden"}</b><i>${leg && leg.configured ? (leg.on ? "te laat" : "op tijd") : "geen entiteit toegewezen"}</i></div>
        <div class="tile"><small>Volgende run</small><b>${runs.length ? hhmm(runs[0].from) : "—"}</b><i>${runs.length ? esc(HEAT_NL[runs[0].kind] || runs[0].kind) + " · " + eur(runs[0].avg_price) : ""}</i></div>
      </div>
      <section class="panel"><div class="pad"><span class="eyebrow">Geplande runs</span></div><div class="scroll-x">
        ${runs.length ? `<table><tr><th>Soort</th><th>Van</th><th>Tot</th><th>kWh</th><th>Gem. prijs</th></tr>${runs.map((r) => `<tr><td>${esc(HEAT_NL[r.kind] || r.kind)}</td><td class="mono">${dayShort(r.from)} ${hhmm(r.from)}</td><td class="mono">${hhmm(r.to)}</td><td class="n">${num(r.kwh, 1)}</td><td class="n">${eur(r.avg_price)}</td></tr>`).join("")}</table>` : `<div class="empty">Geen run gepland: er is nog geen volledige prijsdag.</div>`}
      </div></section>
      <section class="panel pad stack"><span class="eyebrow">Instellingen</span>
        <div class="small">Normale run ${num(o.water_heater_energy_kwh, 1)} kWh in ${o.water_heater_hours} uur; nachtrun ${o.water_heater_night_energy_kwh ? num(o.water_heater_night_energy_kwh, 1) + " kWh" : "geen"};
        legionella ${num(o.water_heater_legionella_energy_kwh, 1)} kWh in ${o.water_heater_legionella_hours} uur op ${DAY_NL[o.water_heater_legionella_weekday] || esc(o.water_heater_legionella_weekday)}.</div>
        <div class="small muted">HEMS plant de boiler nu alleen; de boiler-add-on verwarmt nog zelf. Tanktemperatuur en laatste legionella-run volgen zodra die entiteiten een rol krijgen.</div>${configureLink(s)}</section>
    </div>`;
  }

  _view_net(p, s) {
    return `<div class="stack" style="gap:14px">
      <section class="panel pad stack"><span class="eyebrow">Stroom per fase</span><div id="phases">${phasesHtml(this._hass, s)}</div></section>
      <section class="panel pad stack"><span class="eyebrow">Ruimte voor de auto</span>
        <div class="small">${p && p.ev && p.ev.allowed_a !== null && p.ev.allowed_a !== undefined ? `De krapste fase laat nu <b class="mono">${num(p.ev.allowed_a, 1)} A</b> over voor de auto.` : "Onbekend: geen EV-module of geen fasestromen."}</div>
        <div class="small muted">De load balancer legt nog geen geschiedenis van begrenzingen vast; dat volgt met de live-overgang.</div></section>
    </div>`;
  }

  _view_regie(p, s) {
    if (!s) return `<div class="empty">Instellingen laden…</div>`;
    const o = s.options, r = s.roles;
    const words = settingsInWords(o);
    return `<div class="stack" style="gap:14px">
      ${this._controlBlock(p)}
      <section class="panel pad stack"><div class="row" style="justify-content:space-between"><span class="eyebrow">Instellingen in woorden</span>${configureLink(s)}</div>
        ${words.map(([h, t]) => `<div><b>${h}</b><div class="small" style="color:var(--fg-2)">${t}</div></div>`).join("")}</section>
      <section class="panel"><div class="pad"><span class="eyebrow">Entiteit per rol</span></div><div class="scroll-x"><table>
        ${Object.entries(r).sort().map(([k, v]) => `<tr><td class="mono">${esc(k.replace(/_entity$|_entities$/, ""))}</td><td class="mono">${esc(Array.isArray(v) ? v.join(", ") : String(v))}</td><td class="mono small">${typeof v === "string" && v.includes(".") ? (this._hass.states[v] ? esc(this._hass.states[v].state) : `<span style="color:var(--fault)">ontbreekt</span>`) : ""}</td></tr>`).join("")}
      </table></div></section>
      <div class="small muted mono">paneel ${VERSION} · HEMS build ${esc((p && p.meta.build) || "?")}</div>
    </div>`;
  }

  _controlBlock(p) {
    const c = (p && p.control) || { modes: {}, armed: false };
    const mods = [["battery", "Batterij"], ["ev", "Auto"], ["water_heater", "Boiler"]];
    return `<section class="panel pad stack"><span class="eyebrow">Sturen</span>
      <div class="row"><span class="tag ${c.armed ? "fault" : "ok"}">${c.armed ? "GEWAPEND" : "VEILIG"}</span>
        <button class="btn ${c.armed ? "" : "pri"} hold" data-act="arm">${c.armed ? "Ontwapenen" : "Houd 1,5 s vast om te wapenen"}</button>
        <button class="btn danger" data-act="disarm">Alles naar dry-run</button></div>
      <div class="small muted">Geen enkele module schrijft nog naar een apparaat; wapenen verandert nu niets, maar wordt gelogd. Na een herstart staat de hoofdschakelaar altijd uit.</div>
      ${mods.map(([k, label]) => `<div class="row" style="justify-content:space-between;max-width:560px"><b>${label}</b><span class="seg">
        ${["dry_run", "advisory"].map((m) => `<button data-mode="${k}:${m}" aria-pressed="${(c.modes[k] || "dry_run") === m}">${MODE_NL[m]}</button>`).join("")}
        <button disabled title="Komt met de eerste module die zelf stuurt">AUTO</button></span></div>`).join("")}
      <div class="small muted">Advies: HEMS stelt de volgende actie voor; Toepassen vuurt <span class="mono">hems_recommendation_applied</span> af voor je eigen automatisering.</div>
    </section>`;
  }

  _view_leren(p, s) {
    const r = p && p.realised;
    if (!r) return `<div class="empty">Nog geen metingen.</div>`;
    const days = r.daily || [];
    const err = r.errors || {};
    const errTxt = (e, label) => e ? `<div class="tile"><small>${label} · 7 d</small><b>${num(e.mae_kwh_day, 2)} kWh/d</b><i>bias ${e.bias_kwh_day > 0 ? "+" : ""}${num(e.bias_kwh_day, 2)} · ${e.relative === null ? "" : num(e.relative * 100, 0) + " %"}</i></div>`
      : `<div class="tile"><small>${label}</small><b class="muted">—</b><i>te weinig metingen</i></div>`;
    const qs = (r.quarters || []).slice(-96);
    const actual = (q) => q.battery_kwh > 0.05 ? "charge" : q.battery_kwh < -0.05 ? "discharge" : "idle";
    const norm = (v) => { const x = String(v || "").toLowerCase(); return /charg|laad|laden/.test(x) && !/dis|ont/.test(x) ? "charge" : /dis|ont/.test(x) ? "discharge" : x ? "idle" : null; };
    const hasOther = qs.some((q) => q.other);
    const disagree = qs.filter((q) => q.planned && hasOther && q.other && norm(q.other) !== q.planned).length;
    const b = r.bands || {};
    return `<div class="stack" style="gap:14px">
      <div class="grid4">
        ${errTxt(err.pv, "Zonverwachting")}${errTxt(err.load, "Huisverwachting")}
        <div class="tile"><small>Band zon P10–P90</small><b>${b.pv ? num(b.pv.p10, 2) + "–" + num(b.pv.p90, 2) : "—"}</b><i>${b.pv ? (b.pv.source === "measured" ? "gemeten, " + b.pv.samples + " kw." : "standaard, nog te weinig metingen") : ""}</i></div>
        <div class="tile"><small>Band huis P10–P90</small><b>${b.load ? num(b.load.p10, 2) + "–" + num(b.load.p90, 2) : "—"}</b><i>${b.load ? (b.load.source === "measured" ? "gemeten, " + b.load.samples + " kw." : "standaard, nog te weinig metingen") : ""}</i></div>
      </div>
      <section class="panel"><div class="pad"><span class="eyebrow">Resultaat per dag t.o.v. zelfverbruik</span></div>
        <div style="padding:0 6px 10px"><svg id="days" style="display:block;width:100%"></svg></div></section>
      <section class="panel"><div class="pad row" style="justify-content:space-between"><span class="eyebrow">Laatste 24 uur per kwartier</span>
        ${hasOther ? `<span class="tag ${disagree ? "warn" : "ok"}">${disagree} kwartieren oneens met de oude manager</span>` : `<span class="small muted">Wijs bij Instellingen de actiesensor van de oude battery manager toe voor de vergelijking.</span>`}</div>
        <div class="scroll-x"><table><tr><th>Kwartier</th><th>HEMS zou</th>${hasOther ? "<th>Oude manager</th>" : ""}<th>Batterij deed</th><th>Net</th><th>Zon</th><th>Huis</th><th>Kosten</th><th>Zelfverbr.</th></tr>
        ${qs.slice().reverse().map((q) => { const off = hasOther && q.other && q.planned && norm(q.other) !== q.planned;
          return `<tr style="${off ? "background:var(--discharge-soft)" : ""}"><td class="mono">${dayShort(q.t)} ${hhmm(q.t)}</td><td class="c-${q.planned || "idle"}">${esc(ACTION_NL[q.planned] || q.planned || "—")}</td>
          ${hasOther ? `<td>${esc(q.other || "—")}</td>` : ""}<td class="c-${actual(q)}">${ACTION_NL[actual(q)]} ${num(q.battery_kwh * 4, 1)} kW</td>
          <td class="n">${num((q.import_kwh - q.export_kwh) * 4, 1)} kW</td><td class="n">${num(q.pv_kwh * 4, 1)}${q.fc_pv_kwh !== null && q.fc_pv_kwh !== undefined ? ` <span class="muted">(${num(q.fc_pv_kwh * 4, 1)})</span>` : ""}</td>
          <td class="n">${num(q.load_kwh * 4, 1)}${q.fc_load_kwh !== null && q.fc_load_kwh !== undefined ? ` <span class="muted">(${num(q.fc_load_kwh * 4, 1)})</span>` : ""}</td>
          <td class="n">${q.cost === undefined ? "—" : "€ " + num(q.cost, 3)}</td><td class="n">${q.baseline_cost === undefined ? "—" : "€ " + num(q.baseline_cost, 3)}</td></tr>`; }).join("")}
        </table></div><div class="small muted pad">Tussen haakjes: wat HEMS verwachtte. Kwartieren met minder dan 60 % meettijd tellen niet mee in de totalen.</div></section>
    </div>`;
  }

  _bindActions() {
    const root = this.shadowRoot;
    const on = (sel, fn) => { const b = root.querySelector(sel); if (b) b.addEventListener("click", fn); };
    root.querySelectorAll('[data-act="disarm"]').forEach((b) => b.addEventListener("click", () => this._hass.callService("hems", "disarm_all", {})));
    root.querySelectorAll("[data-apply]").forEach((b) => b.addEventListener("click", () => { this._applyId = b.dataset.apply; this._render(); }));
    root.querySelectorAll("[data-apply-no]").forEach((b) => b.addEventListener("click", () => { this._applyId = null; this._render(); }));
    root.querySelectorAll("[data-apply-yes]").forEach((b) => b.addEventListener("click", () => {
      this._hass.callService("hems", "apply_recommendation", { id: b.dataset.applyYes }); this._applyId = null;
    }));
    root.querySelectorAll("[data-dismiss]").forEach((b) => b.addEventListener("click", () => this._hass.callService("hems", "dismiss_recommendation", { id: b.dataset.dismiss })));
    root.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
      const [module, mode] = b.dataset.mode.split(":");
      this._hass.callService("select", "select_option", { entity_id: `select.hems_${module}_mode`, option: mode });
    }));
    const arm = root.querySelector('[data-act="arm"]');
    if (arm) {
      const armed = store.payload && store.payload.control && store.payload.control.armed;
      if (armed) arm.addEventListener("click", () => this._hass.callService("switch", "turn_off", { entity_id: "switch.hems_master_arm" }));
      else {
        const start = (ev) => { ev.preventDefault(); clearTimeout(this._armTimer); arm.classList.add("holding");
          this._armTimer = setTimeout(() => { this._armTimer = null; this._hass.callService("switch", "turn_on", { entity_id: "switch.hems_master_arm" }); }, 1500); };
        const stop = () => { arm.classList.remove("holding"); clearTimeout(this._armTimer); this._armTimer = null; };
        arm.addEventListener("pointerdown", start); ["pointerup", "pointerleave", "pointercancel"].forEach((e) => arm.addEventListener(e, stop));
      }
    }
    on('[data-act="force"]', () => { this._confirm = true; this._render(); });
    on('[data-act="force-no"]', () => { this._confirm = false; this._render(); });
    on('[data-act="force-yes"]', () => {
      const isOn = this._hass.states["switch.hems_ev_force_charge"] && this._hass.states["switch.hems_ev_force_charge"].state === "on";
      this._hass.callService("switch", isOn ? "turn_off" : "turn_on", { entity_id: "switch.hems_ev_force_charge" });
      this._confirm = false; this._render();
    });
    root.querySelectorAll("[data-nav]").forEach((a) => a.addEventListener("click", (ev) => {
      ev.preventDefault();
      history.pushState(null, "", a.getAttribute("href"));
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    }));
  }
}

const PANEL_CSS = `
:host { min-height:100vh; }
header.top { display:flex; align-items:center; gap:10px; padding:0 12px; height:56px; background:var(--panel); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:2; }
header .title { font:700 20px var(--font-display); letter-spacing:.02em; margin-right:8px; }
nav.tabs { display:flex; gap:2px; overflow-x:auto; scrollbar-width:none; min-width:0; }
nav.tabs button { border:none; background:none; padding:10px 10px 12px; font:600 12px var(--font-data); letter-spacing:.04em; color:var(--fg-3); cursor:pointer; white-space:nowrap; min-height:44px; }
nav.tabs button[aria-selected="true"] { color:var(--fg); box-shadow:inset 0 -2px 0 var(--fg); }
.strip { display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:8px 14px; background:var(--panel); border-bottom:1px solid var(--line); }
.strip .sp { flex:1; }
main { padding:14px; max-width:1600px; margin:0 auto; }
main.kiosk { padding:10px; padding-bottom:64px; }
.grid-nu { display:grid; grid-template-columns:minmax(300px,380px) minmax(0,1fr); gap:14px; align-items:start; }
main.kiosk .grid-nu { grid-template-columns:300px minmax(0,1fr); gap:10px; }
main.kiosk .tiles { grid-template-columns:repeat(2,minmax(0,1fr)); }
svg#tl:focus { outline:none; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr)); gap:14px; }
.grid4 { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr)); gap:8px; }
.legend { display:flex; gap:12px; flex-wrap:wrap; padding:2px 14px 10px; color:var(--fg-2); }
.legend span { display:inline-flex; gap:6px; align-items:center; }
.legend i { width:14px; height:10px; display:inline-block; border-radius:2px; }
nav.ktabs { position:fixed; left:0; right:0; bottom:0; display:flex; background:var(--panel); border-top:1px solid var(--line); }
nav.ktabs button { flex:1; border:none; background:none; padding:14px 0; font:600 13px var(--font-data); color:var(--fg-3); }
nav.ktabs button[aria-pressed="true"] { color:var(--fg); box-shadow:inset 0 2px 0 var(--fg); }
a { color:var(--charge); }
.alerts { display:flex; flex-direction:column; gap:1px; }
.alert { background:var(--discharge-soft); border-bottom:1px solid var(--line); padding:8px 14px; font-size:13px; }
.alert b { color:var(--fault); margin-right:6px; }
.rec { border:1px solid var(--warn); border-radius:5px; padding:10px; display:flex; flex-direction:column; gap:8px; background:var(--panel); }
.hold { position:relative; overflow:hidden; touch-action:none; }
.hold.holding { box-shadow:inset 0 0 0 2px var(--fault); }
`;

function configureLink(s) {
  return s ? `<a data-nav href="/config/integrations/integration/hems" class="small">Wijzig in HEMS-instellingen →</a>` : "";
}

function settingsInWords(o) {
  const yes = (v) => v ? "aan" : "uit";
  return [
    ["Batterij", `${num(o.capacity_kwh, 0)} kWh bruikbaar, max ${num(o.max_power_kw, 1)} kW. Nooit onder ${num(o.hard_min_soc_pct, 0)} %, reserve ${num(o.reserve_soc_pct, 0)} %. Rendement ${num(o.round_trip_eff, 2)}; een cyclus moet € ${num(o.min_profit_margin, 2)} per kWh opleveren na verlies. Wachtkosten € ${num(o.hold_cost_kwh_h, 3)} per kWh per uur.`],
    ["Boiler", o.water_heater_enabled ? `Aan. Dagrun ${num(o.water_heater_energy_kwh, 1)} kWh in ${o.water_heater_hours} u, legionella ${num(o.water_heater_legionella_energy_kwh, 1)} kWh op ${DAY_NL[o.water_heater_legionella_weekday] || esc(o.water_heater_legionella_weekday)}.` : "Uit."],
    ["Auto", o.ev_enabled ? `Aan (dry-run). ${num(o.ev_capacity_kwh, 1)} kWh accu, doel ${num(o.ev_target_required_pct, 0)} % bij deadline, tot ${num(o.ev_target_max_pct, 0)} % onder € ${num(o.ev_max_price, 2)}. ${num(o.ev_min_current_a, 0)}–${num(o.ev_max_current_a, 0)} A per fase; alleen zon voor extra: ${yes(o.ev_solar_only)}.` : "Uit."],
    ["Prijzen", `Nord Pool ${yes(o.nordpool_enabled)} (${esc(o.delivery_area)}). Import ×${num(o.import_vat_multiplier, 2)} + € ${num(o.import_markup, 4)} + energiebelasting € ${num(o.import_energy_tax, 5)}. Saldering ${yes(o.salderen)} tot ${esc(o.salderen_until || "—")}.`],
    ["Zon en weer", `Weer ${yes(o.weather_enabled)}; PV-piek ${num(o.pv_max_ac_w, 0)} W; versterking ${o.pv_gain_w_per_wm2 ? num(o.pv_gain_w_per_wm2, 2) : "automatisch gekalibreerd"}.`],
    ["Netaansluiting", `${num(o.grid_limit_a, 0)} A per fase, ${num(o.grid_margin_a, 0)} A marge.`],
    ["Logboek", `Volledig plan per cyclus loggen: ${yes(o.trace_full_plan)}.`],
  ];
}

function windowsTable(p) {
  const ws = (p && p.windows) || [];
  if (!ws.length) return `<div class="empty">Geen laad- of ontlaadvensters gepland.</div>`;
  return `<table><tr><th>Actie</th><th>Van</th><th>Tot</th><th>kWh</th><th>kW</th><th>Gem. prijs</th><th>SoC</th></tr>
    ${ws.map((w) => `<tr><td class="c-${w.action}">${esc(ACTION_NL[w.action] || w.action)}</td><td class="mono">${dayShort(w.from)} ${hhmm(w.from)}</td><td class="mono">${hhmm(w.to)}</td>
      <td class="n">${num(w.kwh, 1)}</td><td class="n">${kw(Math.abs(w.power_w))}</td><td class="n">${eur(w.avg_price_eur_kwh)}</td><td class="n">${num(w.soc_from_pct, 0)} → ${num(w.soc_to_pct, 0)} %</td></tr>`).join("")}</table>`;
}

function sellTable(p) {
  const ws = (p && p.sell_windows) || [];
  if (!ws.length) return `<div class="empty">Geen verkoopvensters in de horizon.</div>`;
  return `<table><tr><th>Venster</th><th>Piek</th><th>Status</th><th>Verkocht</th><th>Uit voorraad</th></tr>
    ${ws.map((w) => `<tr><td class="mono">${dayShort(w.from)} ${hhmm(w.from)}–${hhmm(w.to)}</td><td class="n">${eur(w.peak)}</td>
      <td><span class="tag ${w.status === "unsold" ? "fault" : w.status === "planned" ? "ok" : "off"}">${esc(WINDOW_NL[w.status] || w.status)}</span></td>
      <td class="n">${num(w.sold_kwh, 1)} kWh</td><td class="n">${num(w.from_stock_kwh, 1)} kWh</td></tr>`).join("")}</table>`;
}

/** Neighbouring EV quarters with the same current and tier as one block: from, to, current, tier, mean import price, PV in the block. */
function evBlocks(quarters) {
  const out = [];
  for (const r of quarters) {
    const t = new Date(r.t).getTime();
    const last = out[out.length - 1];
    if (last && last.end === t && last.a === r.ev_a && last.tier === r.ev_tier) { last.end = t + Q_MS; last.sum += r.imp; last.n += 1; last.pv += r.pv || 0; }
    else out.push({ start: t, end: t + Q_MS, a: r.ev_a, tier: r.ev_tier, sum: r.imp, n: 1, pv: r.pv || 0 });
  }
  return out.map((b) => ({ from: new Date(b.start).toISOString(), to: new Date(b.end).toISOString(), a: b.a, tier: b.tier, price: b.sum / b.n, pv: b.pv }));
}

function cheapestBlock(rows, len) {
  let best = null;
  for (let i = 0; i + len <= rows.length; i++) {
    const avg = rows.slice(i, i + len).reduce((a, r) => a + r.imp, 0) / len;
    if (!best || avg < best.avg) best = { from: rows[i].t, to: new Date(new Date(rows[i + len - 1].t).getTime() + Q_MS).toISOString(), avg };
  }
  return best;
}

function drawHeatmap(host, svg, payload) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const rows = payload.quarters || [];
  const days = [];
  for (const r of rows) { const k = localDayKey(r.t); let d = days.find((x) => x.k === k); if (!d) days.push(d = { k, t: r.t, q: {} }); d.q[localHour(r.t) * 4 + Math.floor(new Date(r.t).getUTCMinutes() / 15)] = r; }
  const C = (v) => cssVar(host, v);
  const W = Math.max(620, svg.getBoundingClientRect().width || 620), L = 70, cw = (W - L - 6) / 96, rh = 34;
  const H = days.length * (rh + 6) + 22;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("height", H);
  const st = priceStats(rows);
  const el = (tag, a) => { const e = document.createElementNS(SVGNS, tag); for (const k in a) e.setAttribute(k, a[k]); svg.appendChild(e); return e; };
  days.forEach((d, j) => {
    const y = j * (rh + 6);
    const t = el("text", { x: 0, y: y + rh / 2 + 4, fill: C("--fg-2"), "font-size": 11 }); t.textContent = dayShort(d.t);
    for (let i = 0; i < 96; i++) {
      const r = d.q[i];
      if (!r) { el("rect", { x: L + i * cw, y, width: cw - .5, height: rh, fill: C("--panel-2") }); continue; }
      const cheap = r.imp < st.avg;
      const a = cheap ? (st.avg - r.imp) / Math.max(1e-6, st.avg - st.min) : (r.imp - st.avg) / Math.max(1e-6, st.max - st.avg);
      const rect = el("rect", { x: L + i * cw, y, width: cw - .5, height: rh, fill: C(cheap ? "--cheap" : "--dear"), "fill-opacity": .15 + .8 * Math.min(1, a) });
      const tt = document.createElementNS(SVGNS, "title"); tt.textContent = `${hhmm(r.t)} · ${eur(r.imp)} €/kWh`; rect.appendChild(tt);
    }
  });
  for (let h = 0; h <= 24; h += 3) { const t = el("text", { x: L + h * 4 * cw, y: H - 4, fill: C("--fg-3"), "font-size": 10, "text-anchor": "middle" }); t.textContent = String(h).padStart(2, "0"); }
}

function drawDays(host, svg, payload) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const days = ((payload.realised && payload.realised.daily) || []).slice(-30);
  const C = (v) => cssVar(host, v);
  const W = Math.max(320, svg.getBoundingClientRect().width || 600), H = 160, L = 46, top = 10, bot = H - 22;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("height", H);
  const el = (tag, a) => { const e = document.createElementNS(SVGNS, tag); for (const k in a) e.setAttribute(k, a[k]); svg.appendChild(e); return e; };
  const t = (txt, a) => { const e = el("text", { fill: C("--fg-3"), "font-size": 10, ...a }); e.textContent = txt; };
  if (!days.length) { t("Nog geen hele dag gemeten", { x: W / 2, y: H / 2, "text-anchor": "middle" }); return; }
  const mx = Math.max(0.1, ...days.map((d) => Math.abs(d.gain)));
  const zero = top + (bot - top) / 2, sy = (v) => zero - v / mx * (bot - top) / 2;
  el("line", { x1: L, x2: W - 4, y1: zero, y2: zero, stroke: C("--line") });
  t("+€ " + num(mx, 2), { x: L - 4, y: top + 8, "text-anchor": "end" }); t("−€ " + num(mx, 2), { x: L - 4, y: bot, "text-anchor": "end" });
  const bw = (W - L - 4) / days.length;
  days.forEach((d, i) => {
    const y = sy(d.gain);
    const r = el("rect", { x: L + i * bw + 1, y: Math.min(y, zero), width: Math.max(1, bw - 2), height: Math.abs(zero - y), fill: C(d.gain >= 0 ? "--ok" : "--fault"), "fill-opacity": d.today ? .5 : .85 });
    const tt = document.createElementNS(SVGNS, "title"); tt.textContent = `${d.date}: ${num(d.gain, 2)} € (kosten ${num(d.cost, 2)}, zelfverbruik ${num(d.baseline_cost, 2)})`; r.appendChild(tt);
    if (days.length <= 14 || i % 3 === 0) t(d.date.slice(5), { x: L + i * bw + bw / 2, y: H - 6, "text-anchor": "middle" });
  });
}

/* ------------------------------------------------------------------ Lovelace cards */

class HemsCardBase extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); }
  setConfig(config) { this._config = config || {}; }
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass; TZ = tzOf(hass); store.attach(hass);
    this.toggleAttribute("dark", this._config && this._config.theme ? this._config.theme === "dark" : !!(hass.themes && hass.themes.darkMode));
    if (first) this.render();
  }
  connectedCallback() { upgradeProperty(this, "hass"); this._off = store.on(() => this.render()); this._ro = new ResizeObserver(() => this.render()); this._ro.observe(this); }
  disconnectedCallback() { if (this._off) this._off(); if (this._ro) this._ro.disconnect(); }
  getCardSize() { return 4; }
}

class HemsTimelineCard extends HemsCardBase {
  render() {
    if (!this._hass) return;
    const hours = Number((this._config && this._config.hours) || 24);
    if (!this.shadowRoot.getElementById("tl")) {
      this.shadowRoot.innerHTML = `<style>${BASE_CSS} :host{background:var(--panel);border-radius:var(--ha-card-border-radius,12px);overflow:hidden}</style>
        <div class="pad" style="padding-bottom:0"><span class="eyebrow">${esc((this._config && this._config.title) || "HEMS · tijdlijn")}</span></div>
        <div style="padding:4px 6px 8px"><svg id="tl" style="display:block;width:100%"></svg></div><div class="pad" id="why" style="border-top:1px solid var(--line)"></div>`;
    }
    const p = store.payload;
    const draw = () => drawTimeline(this, this.shadowRoot.getElementById("tl"), p, {
      hours, lanes: (this._config && this._config.lanes) || ["price", "plan", "soc", "pvload", "devices"], compact: this.clientWidth < 500, selected: this._sel,
      onSelect: (i) => { this._sel = i; this.shadowRoot.getElementById("why").innerHTML = whyHtml(p, i); draw(); },
    });
    if (p) draw();
  }
}

class HemsVerdictCard extends HemsCardBase {
  render() {
    if (!this._hass) return;
    const p = store.payload;
    this.shadowRoot.innerHTML = `<style>${BASE_CSS} :host{background:var(--panel);border-radius:var(--ha-card-border-radius,12px)}</style>
      <div class="pad stack">${verdictHtml(p, Number((this._config && this._config.size) || 30))}${this._config && this._config.chain === false ? "" : chainHtml(p)}</div>`;
  }
  getCardSize() { return 3; }
}

if (!customElements.get("hems-panel")) customElements.define("hems-panel", HemsPanel);
if (!customElements.get("hems-timeline-card")) customElements.define("hems-timeline-card", HemsTimelineCard);
if (!customElements.get("hems-verdict-card")) customElements.define("hems-verdict-card", HemsVerdictCard);
window.customCards = window.customCards || [];
for (const [type, name, description] of [
  ["hems-timeline-card", "HEMS tijdlijn", "Prijs, plan, SoC en verwachtingen op één tijdas, met het waarom per kwartier."],
  ["hems-verdict-card", "HEMS nu", "Wat HEMS nu zou doen, waarom, en de beslisketen."],
]) if (!window.customCards.some((c) => c.type === type)) window.customCards.push({ type, name, description, preview: false });
