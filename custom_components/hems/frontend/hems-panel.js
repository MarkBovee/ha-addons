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
 * URL options: ?kiosk (one screen for the wall tablet), ?theme=dark|light (force a theme), #overview|decisions|insights|settings (older hashes still land on the right view).
 */

const VERSION = "0.8.0";
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
    this._hass = hass;
    if (this._conn === hass.connection) return;
    this._conn = hass.connection;
    // unsubscribing on a connection that is already gone rejects; that is expected after an HA restart
    if (this._unsub) { try { Promise.resolve(this._unsub()).catch(() => {}); } catch (e) { /* connection gone */ } }
    this._unsub = null;
    hass.connection.subscribeMessage((msg) => {
      this.loaded = msg.loaded;
      this.payload = msg.payload;
      this.receivedAt = Date.now();
      this.error = null;
      this._emit();
    }, { type: "hems/subscribe" }).then((unsub) => { this._unsub = unsub; }).catch((err) => {
      this.error = (err && err.message) || "Subscription failed";
      this._emit();
      // after an HA restart the frontend reconnects before HEMS has registered its commands (unknown_command):
      // try again, so a wall tablet recovers without a reload
      this._conn = null;
      clearTimeout(this._retry);
      this._retry = setTimeout(() => this.attach(this._hass), 10000);
    });
    this.refreshSettings(hass);
  }

  refreshSettings(hass) {
    hass.connection.sendMessagePromise({ type: "hems/settings" }).then((s) => { this.settings = s; this._emit(); })
      .catch((err) => { this.settings = null; this.settingsError = (err && err.message) || "no settings"; this._emit(); });
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
  if (!fmtCache[k]) fmtCache[k] = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...opts });
  return fmtCache[k];
}
const hhmm = (d) => d ? fmt("t", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(d)) : "—";
const dayShort = (d) => fmt("d", { weekday: "short", day: "numeric", month: "short" }).format(new Date(d));
const localHour = (d) => Number(fmt("h", { hour: "numeric", hourCycle: "h23" }).format(new Date(d)));
const localDayKey = (d) => fmt("k", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(d));
function num(v, dec = 1) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const x = Math.abs(Number(v)) < 0.5 * 10 ** -dec ? 0 : Number(v);
  return x.toLocaleString("en-GB", { minimumFractionDigits: dec, maximumFractionDigits: dec });
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
  return h < 48 ? h + " h" : Math.round(h / 24) + " d";
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const PERIODS = ["day", "week", "month", "year"];
const PERIOD_LABEL = { day: "Day", week: "Week", month: "Month", year: "Year" };
const PERIOD_NOW = { day: "today", week: "this week", month: "this month", year: "this year" };
const PERIOD_KEEP = { day: 30, week: 26, month: 12, year: 10 };
const OTHER_SELL_W = 2000;                 // the old manager's adaptive discharge at or above this is selling, below it covers the house
const ACTION_LABEL = { charge: "Charge", discharge: "Discharge", idle: "Idle" };
const EXEC_LABEL = {
  as_planned: "as planned", at_floor: "at the floor", limited_floor: "limited by the floor", at_full: "battery full",
  limited_full: "limited: nearly full", no_soc: "no SoC", stale_soc: "SoC stale", expired: "plan expired", no_plan: "no plan",
};
const STATUS_LABEL = {
  ok: "ok", no_soc: "no SoC: HEMS plans nothing", stale_soc: "SoC stale: HEMS plans nothing", no_prices: "no prices",
  no_price_for_now: "no price for this quarter",
};
const EV_LABEL = {
  off: "module off", not_plugged: "not plugged in", no_soc: "no SoC from the car", problem: "charger reports a problem", idle: "nothing to charge",
  planned: "planned", deadline_at_risk: "deadline at risk", forced: "force charging",
};
const WINDOW_LABEL = { planned: "planned", partial: "partial", no_stock: "no stock", kept_for_later: "kept for later", unsold: "unsold" };
const HEAT_LABEL = { night: "night", heating: "heating", legionella: "legionella" };
const DAY_LABEL = { monday: "Monday", tuesday: "Tuesday", wednesday: "Wednesday", thursday: "Thursday", friday: "Friday", saturday: "Saturday", sunday: "Sunday" };
const TIER_LABEL = { deadline: "deadline", cheap: "cheap", forced: "forced", surplus: "solar" };

/* ------------------------------------------------------------------ styles */

const TOKENS = `
:host {
  --bg:#f4f5f7; --panel:#ffffff; --panel-2:#eceef1; --line:#d9dde2; --line-2:#e7eaee;
  --cheap-bar:#c9d8f2; --mid-bar:#dde1e6; --dear-bar:#f1d9c3;
  --fg:#1b2026; --fg-2:#4b5560; --fg-3:#6f7984;
  --charge:#2f6fd0; --charge-soft:rgba(47,111,208,.16);
  --discharge:#c0611a; --discharge-soft:rgba(201,102,26,.16);
  --pv:#9a7800; --pv-soft:rgba(214,170,20,.22);
  --load:#55606b; --load-soft:rgba(85,96,107,.16);
  --grid:#7a4fc4; --grid-soft:rgba(122,79,196,.16);        /* grid import and export: purple, apart from charge blue and solar amber */
  --use:#14857a; --use-soft:rgba(20,133,122,.16);          /* consumption (house, EV, spa): teal */
  --cheap:#2f6fd0; --dear:#c9661a; --mid:#c3c8ce;
  --ok:#2b8a57; --warn:#a87400; --fault:#c2362f; --stale:#7d62a6; --dry:#6b7480;
  --font-display:"Archivo Narrow","Roboto Condensed","Arial Narrow",system-ui,sans-serif;
  --font-body:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --font-data:ui-monospace,"SFMono-Regular","Roboto Mono",Menlo,Consolas,monospace;
}
:host([dark]) {
  --bg:#111418; --panel:#161a1f; --panel-2:#20262e; --line:#2a3038; --line-2:#1f242b;
  --cheap-bar:#2b3a52; --mid-bar:#2a3038; --dear-bar:#4a3a2c;
  --fg:#e6e9ec; --fg-2:#a9b2bc; --fg-3:#8a95a2;
  --charge:#6ea2ef; --charge-soft:rgba(110,162,239,.20);
  --discharge:#f0a05a; --discharge-soft:rgba(240,160,90,.20);
  --pv:#e2bd3a; --pv-soft:rgba(226,189,58,.18);
  --load:#a3adb8; --load-soft:rgba(163,173,184,.14);
  --grid:#b08ef0; --grid-soft:rgba(176,142,240,.20);
  --use:#4cc3b1; --use-soft:rgba(76,195,177,.18);
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
  const font = opts.compact ? 11 : 12;
  const L = 44, R = 8;
  const n = Math.min(rows.length, Math.round(opts.hours * 4));
  const view = rows.slice(0, n);
  const C = (v) => cssVar(host, v);
  const el = (tag, attrs, parent = svg) => { const e = document.createElementNS(SVGNS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.appendChild(e); return e; };
  const txt = (t, x, y, a = {}) => { const e = el("text", { x, y, fill: C("--fg-3"), "font-size": font, ...a }); e.textContent = t; return e; };

  // tall lanes: Mark wants to read details off the chart, not just see its shape
  const laneH = { price: opts.compact ? 80 : 150, plan: opts.compact ? 52 : 84, soc: opts.compact ? 76 : 140, pvload: opts.compact ? 64 : 120, devices: 40 };
  const lanes = opts.lanes.filter((k) => k !== "devices" || view.some((r) => r.ev_a || r.heat));
  let H = 8; for (const k of lanes) H += laneH[k] + 12; H += 22;
  svg.setAttribute("viewBox", `0 0 ${width} ${H}`);
  svg.setAttribute("height", H);
  if (!n) {
    txt("No plan to show", width / 2, H / 2, { "text-anchor": "middle", fill: C("--fg-2") });
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
        const tm = payload.meta && payload.meta.tomorrow_quarters ? "" : " · tomorrow ±13:15";
        txt("prices not known yet" + tm, width - R - 6, top + h / 2, { "text-anchor": "end", fill: C("--fg-3") });
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
      [[b.reserve_kwh, "reserve", "--warn"], [b.floor_kwh, "floor", "--fault"]].forEach(([v, label, c]) => {
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
      txt("EV", L - 4, top + rh, { "text-anchor": "end" });
      txt("heater", L - 4, top + 2 * rh + 4, { "text-anchor": "end" });
      view.forEach((r, i) => {
        if (r.ev_a) el("rect", { x: L + i * qw, y: top + 3, width: qw + .3, height: rh - 2, fill: dry ? "url(#h-charge)" : C("--charge") });
        if (r.heat) el("rect", { x: L + i * qw, y: top + rh + 4, width: qw + .3, height: rh - 2, fill: dry ? "url(#h-discharge)" : C("--discharge") });
      });
    }
    const labels = { price: "price", plan: "plan", soc: "SoC", pvload: "solar/house", devices: "" };
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
  svg.setAttribute("aria-label", `Plan for ${opts.hours} hours: price, actions, SoC and forecasts. Arrow keys pick a quarter.`);
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
      ${stale ? "plan stale · " : ""}cycle ${hhmm(m.cycle_at)} (${age(planAgeMs(p))})</span>
    <span class="row" style="gap:5px"><i class="dot" style="background:var(${m.price_source === "market" ? "--ok" : "--warn"})"></i>prices: ${m.price_source === "market" ? "Nord Pool" : esc(m.price_source || "—")}</span>
    <span class="row" style="gap:5px"><i class="dot" style="background:var(${tomorrow ? "--ok" : "--warn"})"></i>tomorrow: ${tomorrow ? "known" : "not yet"}</span>
    <span class="row" style="gap:5px"><i class="dot" style="background:var(${m.weather_age_min !== null && m.weather_age_min < 90 ? "--ok" : "--warn"})"></i>weather ${m.weather_age_min === null ? "—" : num(m.weather_age_min, 0) + " min"}</span>
    <span>build ${esc(String(m.build || "?").slice(0, 7))}</span>
  </span>`;
}


function alertsHtml(p) {
  const a = (p && p.alerts) || {};
  const label = { data: "Data missing", deadline: "EV deadline at risk", not_executed: "Plan not executed", legionella: "Legionella run overdue" };
  const on = Object.entries(a).filter(([, v]) => v && v.on);
  if (!on.length) return "";
  return `<div class="alerts">${on.map(([k, v]) => `<div class="alert"><b>${label[k] || k}</b> <span>${esc(v.reason || "")}</span></div>`).join("")}</div>`;
}

function recText(r) {
  const x = r.payload || {};
  if (r.module === "battery") return `${ACTION_LABEL[x.action] || x.action} ${hhmm(x.from)}–${hhmm(x.to)} at ${kw(x.power_w)} kW (${num(x.kwh, 1)} kWh)`;
  if (r.module === "ev") return `Charge EV ${hhmm(x.from)}–${hhmm(x.to)} at ${num(x.current_a, 0)} A (${num(x.kwh, 1)} kWh, ${TIER_LABEL[x.tier] || x.tier})`;
  return `Water heater ${HEAT_LABEL[x.kind] || x.kind} ${hhmm(x.from)}–${hhmm(x.to)} (${num(x.kwh, 1)} kWh)`;
}

function recsHtml(p, confirmId) {
  const recs = (p && p.control && p.control.recommendations) || [];
  if (!recs.length) return "";
  return `<section class="stack"><span class="eyebrow">Recommendations</span>${recs.map((r) => `<div class="rec">
    <div class="row" style="justify-content:space-between"><b>${esc(recText(r))}</b>${r.status === "applied" ? `<span class="tag ok">APPLIED ${hhmm(r.applied_at)}</span>` : ""}</div>
    ${r.reason ? `<div class="small muted">${esc(r.reason)}</div>` : ""}
    ${r.status === "applied" ? "" : confirmId === r.id
      ? `<div class="small">HEMS fires <span class="mono">hems_recommendation_applied</span>; your automation carries it out. Continue?</div>
         <div class="row"><button class="btn pri" data-apply-yes="${esc(r.id)}">Yes, apply</button><button class="btn" data-apply-no>Cancel</button></div>`
      : `<div class="row"><button class="btn pri" data-apply="${esc(r.id)}">Apply</button><button class="btn" data-dismiss="${esc(r.id)}">Dismiss</button></div>`}
  </div>`).join("")}</section>`;
}

function verdictHtml(p, big = 32) {
  if (!p) return `<div class="empty">Waiting for the first HEMS cycle…</div>`;
  const d = p.decision;
  if (!d) {
    return `<div class="verdict"><span class="eyebrow">HEMS plans nothing now</span>
      <span class="big" style="font-size:${big}px;color:var(--fault)">${esc(STATUS_LABEL[p.meta.status] || p.meta.status)}</span>
      <span class="why">As soon as the missing data is back, HEMS plans again within a minute. Prices and forecasts stay visible.</span></div>`;
  }
  const e = p.execution;
  const act = d.action || "idle";
  const w = e && e.code !== "no_plan" ? e.power_w : d.power_w;
  const c = d.compare || {};
  const best = c.code === "sell" ? "sell" : c.code === "buy" ? "buy" : c.code === "hold" ? "keep" : null;
  const tile = (k, label, v, extra = "") => `<div class="${best === k ? "win" : ""}"><small>${label}</small><b>${eur(v)}</b>${extra}</div>`;
  const later = c.best_sell_later ? `<small>best later ${hhmm(c.best_sell_later.at)} · ${eur(c.best_sell_later.value)}</small>` : "";
  return `<div class="verdict">
    <div class="row" style="align-items:baseline;gap:10px">
      <span class="would" title="Dry-run: this is what HEMS would do; nothing is sent">WOULD</span>
      <span class="big c-${act}" style="font-size:${big}px">${ACTION_LABEL[act] || act}${act !== "idle" ? " " + kw(Math.abs(w)) + " kW" : ""}</span>
    </div>
    <div class="why">${esc(d.reason || "")}</div>
    <div class="cmp">${tile("sell", "sell now", c.sell)}${tile("keep", "keep", c.keep, later)}${tile("buy", "buy now", c.buy)}</div>
    <div class="small muted mono">€ per stored kWh · import ${eur(d.import_price)} · export ${eur(d.export_price)} · SoC ${num(d.soc_pct, 0)} %</div>
  </div>`;
}

function chainHtml(p) {
  if (!p || !p.decision) return "";
  const e = p.execution;
  return `<div class="chain" aria-label="Decision chain">
    <div><b>Proposal</b>${kw(p.decision.power_w)} kW</div>
    <div><b>Engine</b>${kw(e.planned_w)} kW</div>
    <div class="${e.overridden ? "ovr" : ""}" title="${esc(e.reason || "")}"><b>Executor</b>${kw(e.power_w)} kW · ${esc(EXEC_LABEL[e.code] || e.code)}</div>
    <div><b>Sent</b>— dry-run</div>
  </div>${e.overridden ? `<div class="small" style="color:var(--discharge);margin-top:4px">Executor deviates: ${esc(e.reason)}</div>` : ""}`;
}


function whyHtml(p, i) {
  const rows = (p && p.quarters) || [];
  const r = rows[i];
  if (!r) return `<div class="empty">Tap a quarter in the timeline to see why.</div>`;
  const prev = p.diff && p.diff.previous_soc ? p.diff.previous_soc[r.t] : undefined;
  const changed = (p.diff && p.diff.runs || []).find((x) => x.from <= r.t && r.t < x.to);
  const cap = p.battery.capacity_kwh;
  const end = new Date(new Date(r.t).getTime() + Q_MS);
  return `<div class="stack">
    <span class="eyebrow">${dayShort(r.t)} · ${hhmm(r.t)}–${hhmm(end)}</span>
    <div class="row" style="align-items:baseline"><b class="c-${r.act || "idle"}" style="font:700 22px var(--font-display)">${r.act ? (ACTION_LABEL[r.act] || r.act) : "Not planned"}${r.w ? " " + kw(Math.abs(r.w)) + " kW" : ""}</b>
      ${r.act ? `<span class="would">WOULD</span>` : ""}</div>
    ${r.why ? `<div class="small" style="color:var(--fg-2)">${esc(r.why)}</div>` : ""}
    <div class="kv">
      <span>Import / export</span><span>${eur(r.imp)} / ${eur(r.exp)} €/kWh</span>
      <span>Sell · keep · buy</span><span>${eur(r.sell)} · ${eur(r.keep)} · ${eur(r.buy)}</span>
      <span>SoC after quarter</span><span>${r.soc === null ? "—" : num(r.soc, 1) + " kWh (" + num(r.soc / cap * 100, 0) + " %)"}</span>
      ${prev !== undefined ? `<span>Previous plan</span><span>${num(prev, 1)} kWh</span>` : ""}
      <span>Solar / house (forecast)</span><span>${num((r.pv ?? 0) * 4, 2)} / ${num((r.load ?? 0) * 4, 2)} kW</span>
      ${r.ev_a ? `<span>EV</span><span>${num(r.ev_a, 0)} A · ${esc(TIER_LABEL[r.ev_tier] || r.ev_tier || "")}</span>` : ""}
      ${r.heat ? `<span>Water heater</span><span>${esc(HEAT_LABEL[r.heat] || r.heat)}</span>` : ""}
    </div>
    ${changed ? `<div class="small" style="color:var(--warn)">Changed from the previous plan: was ${esc(ACTION_LABEL[changed.was] || changed.was)}, now ${esc(ACTION_LABEL[changed.now] || changed.now)}.</div>` : ""}
    <div class="small muted">Forecasts are estimates; the solar and house forecast can be well off per quarter.</div>
  </div>`;
}

function diffHtml(p) {
  const d = p && p.diff;
  if (!d || !d.available) return `<div class="small muted">No previous plan to compare with yet (first cycle after a restart).</div>`;
  if (!d.runs.length) return `<div class="small muted">No actions changed since the plan of ${hhmm(d.previous_at)}.</div>`;
  return `<div class="stack small">${d.runs.slice(0, 6).map((x) => `<div><b class="mono">${hhmm(x.from)}–${hhmm(x.to)}</b> ${esc(ACTION_LABEL[x.was] || x.was)} → <b class="c-${x.now}">${esc(ACTION_LABEL[x.now] || x.now)}</b>
    ${x.reason ? `<div class="muted">${esc(x.reason)}</div>` : ""}</div>`).join("")}
    ${d.runs.length > 6 ? `<div class="muted">… and ${d.runs.length - 6} more</div>` : ""}</div>`;
}


function phasesHtml(hass, settings) {
  const r = (settings && settings.roles) || {};
  const o = (settings && settings.options) || {};
  const lim = Number(o.grid_limit_a || 25), margin = Number(o.grid_margin_a || 1);
  const ids = ["meter_current_l1_entity", "meter_current_l2_entity", "meter_current_l3_entity"].map((k) => r[k]);
  if (!ids.some(Boolean)) return `<div class="small muted">No phase current entities assigned (Settings → roles).</div>`;
  return `<div class="stack">${ids.map((id, i) => {
    const v = stateNum(hass, id);
    const stale = v === null;
    const pct = v === null ? 0 : Math.min(100, Math.abs(v) / lim * 100);
    const color = v !== null && Math.abs(v) > lim - margin ? "--fault" : v !== null && Math.abs(v) > (lim - margin) * .8 ? "--warn" : "--load";
    return `<div class="row mono small" style="display:grid;grid-template-columns:24px 1fr 76px;gap:8px" title="${esc(id || "")}">
      <b>L${i + 1}</b><div class="bar ${stale ? "stale-frame" : ""}"><i style="width:${pct}%;background:var(${color})"></i><em style="left:${(lim - margin) / lim * 100}%;background:var(--fault)"></em></div>
      <span style="text-align:right">${v === null ? "—" : num(v, 1) + " A"}</span></div>`;
  }).join("")}<div class="small muted mono">limit ${num(lim, 0)} A − margin ${num(margin, 0)} A per phase</div></div>`;
}

/** A property set before the element was defined hides the class setter; move it through the setter. */
function upgradeProperty(el, prop) {
  if (Object.prototype.hasOwnProperty.call(el, prop)) { const v = el[prop]; delete el[prop]; el[prop] = v; }
}

/* ------------------------------------------------------------------ the calm layout: helpers */

/** "today", "tomorrow" or a short weekday for a moment, relative to now, in the HA time zone. */
function dayWord(d) {
  const k = localDayKey(d), today = localDayKey(Date.now()), tomorrow = localDayKey(Date.now() + 864e5);
  return k === today ? "today" : k === tomorrow ? "tomorrow" : fmt("wd", { weekday: "short" }).format(new Date(d));
}

/** Minutes as "2 h 15 min", "45 min" or "3 h". */
function duration(min) { if (min === null || min === undefined) return ""; const h = Math.floor(min / 60), m = Math.round(min % 60); return h ? `${h} h${m ? " " + m + " min" : ""}` : `${m} min`; }

/** A window as "tomorrow 11:30–15:15" (no day word for today). */
function span(from, to) { const w = dayWord(from); return `${w === "today" ? "" : w + " "}${hhmm(from)}–${hhmm(to)}`; }

/** The next battery window of one action that has not ended yet. */
function nextWindow(p, action) {
  const now = Date.now();
  return ((p && p.windows) || []).find((w) => w.action === action && new Date(w.to).getTime() > now) || null;
}

/** What HEMS would do now as one sentence, plus the reason behind it in plain words. */
function headline(p) {
  const d = p && p.decision;
  if (!d) return { lead: STATUS_LABEL[(p && p.meta.status)] || "HEMS plans nothing now", rest: "", why: "As soon as the missing data is back, HEMS plans again within a minute." };
  const act = d.action || "idle";
  // idle is self-consumption: the battery follows the house and keeps the grid at zero (battery-manager calls it adaptive).
  // No power in the headline: it is set once per cycle, the live numbers are in the energy flow and the live charts.
  const lead = act === "charge" ? "Charging from the grid." : act === "discharge" ? "Selling to the grid." : "Adaptive: keeping the grid at zero.";
  const ch = nextWindow(p, "charge"), dis = nextWindow(p, "discharge");
  const parts = [];
  if (ch && act !== "charge") parts.push({ word: "charge", w: ch, cls: "c-charge" });
  if (dis && act !== "discharge") parts.push({ word: "sell", w: dis, cls: "c-discharge" });
  parts.sort((a, b) => new Date(a.w.from) - new Date(b.w.from));
  // a window with pauses gets its active time: a sale between 16:30 and 19:30 with gaps is not three hours of selling
  const paused = (x) => x.active_min && x.active_min < (new Date(x.to) - new Date(x.from)) / 60000 - 1;
  const rest = parts.length ? "Next: " + parts.map((x) => `${x.word} <span class="${x.cls}">${esc(span(x.w.from, x.w.to))}</span>${paused(x.w) ? ` (${duration(x.w.active_min)})` : ""}`).join(", then ") : "";
  const c = d.compare || {};
  const why = c.code === "hold" || c.code === "floor" ? `Sell ${eur(c.sell, 3)} · keep ${eur(c.keep, 3)} €/kWh — ${c.code === "floor" ? "at the sell floor" : "worth more later"}.`
    : c.code === "sell" ? `Sell ${eur(c.sell, 3)} · keep ${eur(c.keep, 3)} €/kWh — selling pays more.`
    : c.code === "buy" ? `Buy ${eur(c.buy, 3)} · keep ${eur(c.keep, 3)} €/kWh — cheaper now than later.`
    : esc(d.reason || "");
  return { lead, rest: rest ? rest + "." : "", why };
}

/** Problems that deserve attention; an empty list means the status pill stays calm. */
function problems(p) {
  if (!p) return ["waiting for the first cycle"];
  const m = p.meta, out = [];
  if (m.status !== "ok") out.push(STATUS_LABEL[m.status] || m.status);
  if (planStale(p)) out.push("plan is stale");
  if (m.price_source !== "market") out.push("no market prices");
  if (m.weather_age_min === null || m.weather_age_min > 90) out.push("weather forecast is old");
  return out;
}

/** The status pill: calm when everything is fine, named problems otherwise. */
function pillHtml(p) {
  const bad = problems(p);
  const armed = p && p.control && p.control.armed;
  const mode = armed ? "Armed" : "Dry-run";
  return `<button type="button" class="pill ${bad.length ? "bad" : ""}" data-act="details" aria-expanded="false">
    <i class="dot" style="background:var(${bad.length ? "--warn" : "--ok"})"></i>${mode} · ${bad.length ? esc(bad.join(", ")) : "all data fresh"}</button>`;
}

/** Three live numbers: solar, grid and battery, refreshed with every state change. */
function liveNumbersHtml(hass, p, s) {
  const r = (s && s.roles) || {};
  const pvIds = [r.pv_entity, ...(r.pv_extra_entities || [])].filter(Boolean);
  const pv = pvIds.length ? pvIds.map((id) => stateNum(hass, id)).reduce((a, b) => (a === null || b === null) ? null : a + b, 0) : null;
  const grid = stateNum(hass, r.grid_entity);
  const soc = stateNum(hass, r.soc_entity);
  const bp = stateNum(hass, r.battery_power_entity);
  const battW = bp === null ? null : bp * (r.battery_power_positive_is_discharging === false ? 1 : -1);    // + charging
  const cell = (label, value, unit, sub) => `<div><dt>${label}</dt><dd>${value}<small> ${unit}</small></dd><span class="sub">${sub}</span></div>`;
  return `<dl class="live">
    ${cell("Solar", pv === null ? "—" : kw(pv), "kW", "&nbsp;")}
    ${cell("Grid", grid === null ? "—" : kw(grid), "kW", grid === null ? "&nbsp;" : grid < 0 ? "export" : "import")}
    ${cell("Battery", soc === null ? "—" : num(soc, 0), "%", battW === null ? "&nbsp;" : Math.abs(battW) < 50 ? "idle" : `${battW > 0 ? "charging" : "discharging"} ${kw(Math.abs(battW))} kW`)}
  </dl>`;
}

/** Everything that is planned from now on, for every device, as one time-ordered list. */
function agenda(p) {
  if (!p) return [];
  const now = Date.now();
  const items = [];
  for (const w of p.windows || []) {
    items.push({ from: w.from, to: w.to, cls: `c-${w.action}`, what: `Battery · ${w.action === "charge" ? "charge" : "sell"} ${w.active_min ? duration(w.active_min) + ", " : ""}${num(w.kwh, 1)} kWh, ${num(w.soc_from_pct, 0)} → ${num(w.soc_to_pct, 0)} %`, price: w.avg_price_eur_kwh });
  }
  for (const h of p.heating || []) items.push({ from: h.from, to: h.to, cls: "", what: `Water heater · ${HEAT_LABEL[h.kind] || h.kind} run, ${num(h.kwh, 1)} kWh`, price: h.avg_price });
  for (const b of evBlocks((p.quarters || []).filter((r) => r.ev_a))) items.push({ from: b.from, to: b.to, cls: "c-charge", what: `EV · ${num(b.a, 0)} A, ${TIER_LABEL[b.tier] || b.tier}`, price: b.price });
  return items.filter((x) => new Date(x.to).getTime() > now).sort((a, b) => new Date(a.from) - new Date(b.from));
}

/** The agenda as rows, or a calm line when nothing is planned. */
function agendaHtml(p, limit = 6) {
  const items = agenda(p).slice(0, limit);
  if (!items.length) return `<p class="quiet">Nothing planned in the known prices.</p>`;
  return `<div class="agenda">${items.map((x) => `<span class="mono ${x.cls}">${esc(span(x.from, x.to))}</span><span>${esc(x.what)}</span><span class="mono quiet">${eur(x.price, 3)}</span>`).join("")}</div>`;
}

/** One line on the EV for the Today view. */
function evLine(p) {
  const ev = p && p.ev;
  if (!ev) return "";
  const dl = ev.deadline ? ` · next deadline ${dayWord(ev.deadline)} ${hhmm(ev.deadline)}` : "";
  return `EV ${esc(EV_LABEL[ev.status] || ev.status)}${dl}`;
}

/** A mode switch for one module: dry-run and advisory, auto shown but not offered yet. */
function modeSegHtml(p, module) {
  const c = (p && p.control) || { modes: {} };
  const cur = (c.modes && c.modes[module]) || "dry_run";
  return `<div class="seg" role="group" aria-label="Mode">${["dry_run", "advisory"].map((m) => `<button type="button" data-mode="${module}:${m}" aria-pressed="${cur === m}">${m === "dry_run" ? "Dry-run" : "Advisory"}</button>`).join("")}<button type="button" disabled title="Comes with the first module that controls a device">Auto</button></div>`;
}

/**
 * The Today chart: import price as bars per quarter, the battery state of charge as a line on the same box, and the
 * plan as a band underneath (charge, sell, EV, water heater). One axis of time, no separate lanes.
 */
function drawCombined(host, svg, payload, hours, big) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const rows = ((payload && payload.quarters) || []).slice(0, Math.round(hours * 4));
  const width = Math.max(320, Math.round(svg.getBoundingClientRect().width || svg.parentNode.clientWidth || 800));
  const C = (v) => cssVar(host, v);
  const font = big ? 15 : 12;
  const H = big ? 330 : 300, top = 18, base = H - (big ? 74 : 66), bandY = base + 12, axisY = H - 6;
  svg.setAttribute("viewBox", `0 0 ${width} ${H}`); svg.setAttribute("height", H);
  const el = (tag, a) => { const e = document.createElementNS(SVGNS, tag); for (const k in a) e.setAttribute(k, a[k]); svg.appendChild(e); return e; };
  const txt = (t, a) => { const e = el("text", { fill: C("--fg-3"), "font-size": font, ...a }); e.textContent = t; return e; };
  if (!rows.length) { txt("No plan to show", { x: width / 2, y: H / 2, "text-anchor": "middle" }); return; }
  const n = rows.length, qw = width / n;
  const imps = rows.map((r) => r.imp);
  const lo = Math.min(0, Math.floor(Math.min(...imps) * 20) / 20), hi = Math.max(0.1, Math.ceil(Math.max(...imps) * 20) / 20);
  const py = (v) => base - (v - lo) / (hi - lo) * (base - top);
  const avg = imps.reduce((a, b) => a + b, 0) / n;
  rows.forEach((r, i) => {
    const fill = r.imp < avg - 0.03 ? "--cheap-bar" : r.imp > avg + 0.05 ? "--dear-bar" : "--mid-bar";
    el("rect", { x: i * qw + .5, y: py(r.imp), width: Math.max(1, qw - 1), height: Math.max(0, base - py(r.imp)), fill: C(fill) });
  });
  // the cheapest and dearest quarter get their price written on them
  const iMin = imps.indexOf(Math.min(...imps)), iMax = imps.indexOf(Math.max(...imps));
  txt(eur(imps[iMax], 3), { x: (iMax + .5) * qw, y: py(imps[iMax]) - 6, "text-anchor": "middle", fill: C("--discharge") });
  txt(eur(imps[iMin], 3), { x: (iMin + .5) * qw, y: py(imps[iMin]) - 6, "text-anchor": "middle", fill: C("--charge") });
  // state of charge on the same box, 0-100 %
  const cap = (payload.battery && payload.battery.capacity_kwh) || 25;
  const sy = (kwh) => base - kwh / cap * (base - top);
  let d = "", on = false;
  rows.forEach((r, i) => { if (r.soc === null || r.soc === undefined) { on = false; return; } d += `${on ? "L" : "M"}${((i + .5) * qw).toFixed(1)},${sy(r.soc).toFixed(1)}`; on = true; });
  el("path", { d, fill: "none", stroke: C("--fg"), "stroke-width": big ? 3 : 2.5, "stroke-linejoin": "round" });
  // the plan band: runs of the same action become one rounded bar
  const runs = (key) => { const out = []; rows.forEach((r, i) => { const k = key(r); const last = out[out.length - 1]; if (k && last && last.k === k && last.end === i) last.end = i + 1; else if (k) out.push({ k, start: i, end: i + 1 }); }); return out; };
  const bh = big ? 14 : 10;
  for (const r of runs((q) => q.act === "charge" || q.act === "discharge" ? q.act : null)) {
    el("rect", { x: r.start * qw, y: bandY, width: (r.end - r.start) * qw, height: bh, rx: bh / 2, fill: C(r.k === "charge" ? "--charge" : "--discharge") });
  }
  for (const r of runs((q) => (q.ev_a ? "ev" : null))) el("rect", { x: r.start * qw, y: bandY + bh + 4, width: (r.end - r.start) * qw, height: 5, rx: 2.5, fill: C("--charge") });
  for (const r of runs((q) => (q.heat ? "heat" : null))) el("rect", { x: r.start * qw, y: bandY + bh + 4, width: (r.end - r.start) * qw, height: 5, rx: 2.5, fill: C("--fg-3") });
  // hour labels and the now line
  const t0 = new Date(rows[0].t).getTime();
  const step = hours > 30 ? 6 : 3;
  rows.forEach((r, i) => {
    const ms = new Date(r.t).getTime();
    if (new Date(ms).getUTCMinutes() !== 0) return;
    const h = localHour(ms);
    if (h % step !== 0) return;
    txt(String(h).padStart(2, "0"), { x: i * qw, y: axisY, "text-anchor": i ? "middle" : "start" });
    if (h === 0) el("line", { x1: i * qw, x2: i * qw, y1: top, y2: base, stroke: C("--line"), "stroke-dasharray": "2 3" });
  });
  const nowX = (Date.now() - t0) / (n * Q_MS) * width;
  if (nowX >= 0 && nowX <= width) el("line", { x1: nowX, x2: nowX, y1: 0, y2: bandY + bh, stroke: C("--fg"), "stroke-width": 1.5 });
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Next ${hours} hours: price per quarter, battery level and the planned charge and sell windows.`);
}

/* ------------------------------------------------------------------ overview: icons, energy flow, weather, solar */

/** Inline stroke icons (no icon font in a shadow root); they take the text colour unless a stroke is given. */
const icon = (paths, size = 18, stroke = "currentColor") => `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${stroke}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
const ICON_PATH = {
  sun: '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"></path>',
  cloud: '<path d="M7 18h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.5A3.3 3.3 0 0 0 7 18z"></path>',
  cloudSun: '<circle cx="8" cy="8" r="3"></circle><path d="M8 2.5v1M2.5 8h1M4.1 4.1l.7.7M11.9 4.1l-.7.7M4.1 11.9l.7-.7"></path><path d="M10 20h7a3.5 3.5 0 0 0 0-7 4.5 4.5 0 0 0-8.6 1.2A2.9 2.9 0 0 0 10 20z"></path>',
  cloudMoon: '<path d="M8.5 3A4.5 4.5 0 1 0 13.6 9.2 3.6 3.6 0 0 1 8.5 3z"></path><path d="M10 20h7a3.5 3.5 0 0 0 0-7 4.5 4.5 0 0 0-8.6 1.2A2.9 2.9 0 0 0 10 20z"></path>',
  drizzle: '<path d="M7 15h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.5A3.3 3.3 0 0 0 7 15z"></path><path d="M8 18.5v.5M12 20v.5M16 18.5v.5"></path>',
  rain: '<path d="M7 15h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.5A3.3 3.3 0 0 0 7 15z"></path><path d="M8 18l-1 3M12 18l-1 3M16 18l-1 3"></path>',
  snow: '<path d="M7 15h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.5A3.3 3.3 0 0 0 7 15z"></path><path d="M8 17.5v3.5M6.5 18.4l3 1.7M6.5 20.1l3-1.7M16 17.5v3.5M14.5 18.4l3 1.7M14.5 20.1l3-1.7"></path>',
  storm: '<path d="M7 15h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.5A3.3 3.3 0 0 0 7 15z"></path><path d="M12 15l-2 4h3l-2 4"></path>',
  fog: '<path d="M4 9h16M4 13h16M6 17h12"></path>',
  grid: '<path d="M8 21l4-18 4 18M6 8h12M5 13h14M9.5 13l5 8M14.5 13l-5 8"></path>',
  house: '<path d="M3 11l9-7 9 7"></path><path d="M5 10v10h14V10"></path><path d="M10 20v-5h4v5"></path>',
  battery: '<rect x="3" y="7" width="16" height="10" rx="2"></rect><path d="M21 11v2"></path><path d="M7 10v4M10 10v4"></path>',
  car: '<path d="M5 16l1.5-5a2 2 0 0 1 1.9-1.4h7.2a2 2 0 0 1 1.9 1.4L19 16"></path><rect x="3" y="16" width="18" height="3" rx="1"></rect><circle cx="7.5" cy="19.5" r="1.5"></circle><circle cx="16.5" cy="19.5" r="1.5"></circle>',
  tank: '<rect x="7" y="3" width="10" height="18" rx="4"></rect><path d="M12 8c-1.5 2-2 3-2 4a2 2 0 0 0 4 0c0-1-.5-2-2-4z"></path>',
  spa: '<path d="M3 15h18v3a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3z"></path><path d="M8 11c0-1.5 1-1.5 1-3s-1-1.5-1-3M12 11c0-1.5 1-1.5 1-3s-1-1.5-1-3M16 11c0-1.5 1-1.5 1-3s-1-1.5-1-3"></path>',
};
const ICON = Object.fromEntries(Object.entries(ICON_PATH).map(([k, v]) => [k, icon(v)]));
/** A WMO weather code (Open-Meteo) as a label and an icon; at night a clear or partly cloudy sky gets no sun. */
function sky(code, isDay = true) {
  const c = Number(code);
  const [label, ic] = c === 0 ? ["Clear", isDay ? "sun" : "moon"] : c <= 2 ? [c === 1 ? "Mostly clear" : "Partly cloudy", isDay ? "cloudSun" : "cloudMoon"]
    : c === 3 ? ["Overcast", "cloud"] : c <= 48 ? ["Fog", "fog"] : c <= 57 ? ["Drizzle", "drizzle"] : c <= 67 ? ["Rain", "rain"]
    : c <= 77 ? ["Snow", "snow"] : c <= 82 ? ["Showers", "rain"] : c <= 86 ? ["Snow showers", "snow"] : ["Thunderstorms", "storm"];
  return { label, icon: ic };
}

/** A power entity in watts, whatever unit it reports (W or kW); null when unknown. */
function watts(hass, entityId) {
  const v = stateNum(hass, entityId);
  if (v === null) return null;
  const unit = hass.states[entityId].attributes.unit_of_measurement;
  return unit === "kW" ? v * 1000 : v;
}

/**
 * The live energy flow: sources (solar, grid, battery) into the house and the house out to its consumers (the active modules
 * and the rest of the house). A link that carries power is drawn wide with moving dashes in the direction of the flow.
 * The house load follows the planner's balance (below), the rest of the house is that minus the metered modules.
 */
function flowHtml(hass, p, s, vertical = false) {
  const r = (s && s.roles) || {};
  const o = (s && s.options) || {};
  const pvIds = [r.pv_entity, ...(r.pv_extra_entities || [])].filter(Boolean);
  const pv = pvIds.length ? pvIds.map((id) => watts(hass, id)).reduce((a, b) => (a === null || b === null) ? null : a + b, 0) : null;
  const grid = watts(hass, r.grid_entity);
  const soc = stateNum(hass, r.soc_entity);
  const bp = watts(hass, r.battery_power_entity);
  const batt = bp === null ? null : bp * (r.battery_power_positive_is_discharging === false ? 1 : -1);    // + charging
  // the same balance as the planner (adapters.house_load): grid + inverter output when there is an inverter sensor, else grid + solar − battery
  const inv = r.inverter_output_entity ? watts(hass, r.inverter_output_entity) : null;
  const house = grid === null ? null : inv !== null ? Math.max(0, grid + inv) : pv === null || batt === null ? null : Math.max(0, pv + grid - batt);
  const ev = o.ev_enabled ? watts(hass, r.ev_power_entity) : null;
  const spa = o.spa_enabled ? watts(hass, r.spa_power_entity) : null;
  const rest = house === null ? null : Math.max(0, house - (ev || 0) - (spa || 0));
  const on = (w) => w !== null && Math.abs(w) >= 50;
  const kwTxt = (w) => w === null ? "—" : `${kw(Math.abs(w))} kW`;
  const wh = o.water_heater_enabled && r.water_heater_entity ? hass.states[r.water_heater_entity] : null;
  const whTemp = wh ? wh.attributes.current_temperature : null;
  const spaClimate = o.spa_enabled && r.spa_climate_entity ? hass.states[r.spa_climate_entity] : null;
  const evPlugged = r.ev_plugged_entity && hass.states[r.ev_plugged_entity] ? hass.states[r.ev_plugged_entity].state === "on" : null;
  // each flow has its own colour: solar amber, grid purple, battery blue while charging and orange while discharging, use teal
  const battColour = batt !== null && on(batt) && batt < 0 ? "--discharge" : "--charge";
  const sources = [
    { label: "Solar", icon: icon(ICON_PATH.sun, 22, "var(--pv)"), value: kwTxt(pv), sub: "", w: pv, colour: "--pv", out: true },
    { label: "Grid", icon: icon(ICON_PATH.grid, 22, "var(--grid)"), value: kwTxt(grid), sub: grid === null || !on(grid) ? "" : grid > 0 ? "import" : "export", w: grid, colour: "--grid", out: grid === null || grid >= 0 },
    { label: "Battery", icon: icon(ICON_PATH.battery, 22, `var(${battColour})`), value: soc === null ? "—" : `${num(soc, 0)} %`, sub: batt === null || !on(batt) ? "idle" : `${batt > 0 ? "charging" : "discharging"} ${kwTxt(batt)}`, w: batt, colour: battColour, out: batt === null || batt <= 0 },
  ];
  const sinks = [{ label: "Home", icon: icon(ICON_PATH.house, 22, "var(--use)"), value: kwTxt(rest), sub: "", w: rest, colour: "--use" }];
  if (o.ev_enabled) sinks.push({ label: "EV", icon: icon(ICON_PATH.car, 22, "var(--use)"), value: kwTxt(ev), sub: evPlugged === false ? "not plugged in" : "", w: ev, colour: "--use" });
  if (o.water_heater_enabled) sinks.push({ label: "Water heater", icon: icon(ICON_PATH.tank, 22, "var(--use)"), value: whTemp === null || whTemp === undefined ? "—" : `${num(whTemp, 0)} °C`, sub: "", w: null, colour: "--use" });
  if (o.spa_enabled) sinks.push({ label: "Spa", icon: icon(ICON_PATH.spa, 22, "var(--use)"), value: spa === null ? (spaClimate && spaClimate.attributes.current_temperature !== undefined ? `${num(spaClimate.attributes.current_temperature, 1)} °C` : "—") : kwTxt(spa), sub: "", w: spa, colour: "--use" });
  const label = `Solar ${kwTxt(pv)}, grid ${kwTxt(grid)}, battery ${sources[2].sub}, house ${kwTxt(house)}`;
  return flowLayout({ sources, sinks, house: kwTxt(house), on, label, vertical });
}

/**
 * Draws the flow in a 1000 x 1000 box scaled to the container: sources, the house in the middle, consumers.
 * Wide: three columns left to right. Vertical (phones): sources on top, the house, consumers below, so nothing scrolls sideways.
 */
function flowLayout({ sources, sinks, house, on, label, vertical }) {
  const spread = (n, i, lo, hi) => n === 1 ? (lo + hi) / 2 : lo + i * ((hi - lo) / (n - 1));
  // node centres in box units, and where lines meet the house
  const src = sources.map((_, i) => vertical ? [spread(sources.length, i, 170, 830), 90] : [100, spread(sources.length, i, 180, 820)]);
  const snk = sinks.map((_, i) => vertical ? [spread(sinks.length, i, sinks.length > 3 ? 125 : 170, sinks.length > 3 ? 875 : 830), 910] : [890, spread(sinks.length, i, 130, 870)]);
  const houseIn = vertical ? [500, 400] : [400, 500], houseOut = vertical ? [500, 600] : [600, 500];
  const srcEdge = (c) => vertical ? [c[0], 175] : [200, c[1]], snkEdge = (c) => vertical ? [c[0], 825] : [780, c[1]];
  const curve = ([x1, y1], [x2, y2]) => vertical ? `M${x1} ${y1} C${x1} ${(y1 + y2) / 2} ${x2} ${(y1 + y2) / 2} ${x2} ${y2}` : `M${x1} ${y1} C${(x1 + x2) / 2} ${y1} ${(x1 + x2) / 2} ${y2} ${x2} ${y2}`;
  const link = (a, b, live, colour, reverse) => live
    ? `<path d="${curve(a, b)}" stroke="var(${colour})" stroke-width="10" fill="none" stroke-linecap="round" opacity=".22" vector-effect="non-scaling-stroke"></path><path class="flow${reverse ? " rev" : ""}" d="${curve(a, b)}" stroke="var(${colour})" stroke-width="2.5" fill="none" stroke-dasharray="4 8" stroke-linecap="round" vector-effect="non-scaling-stroke"></path>`
    : `<path d="${curve(a, b)}" stroke="var(--line)" stroke-width="1.5" fill="none" vector-effect="non-scaling-stroke"></path>`;
  const svg = `<svg class="flow-lines" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
    ${sources.map((x, i) => link(srcEdge(src[i]), houseIn, on(x.w), x.colour, !x.out)).join("")}
    ${sinks.map((x, i) => link(houseOut, snkEdge(snk[i]), on(x.w), x.colour, false)).join("")}</svg>`;
  const node = (x, [cx, cy]) => `<div class="fnode ${on(x.w) ? "on" : ""}" style="left:${cx / 10}%;top:${cy / 10}%;--c:var(${x.colour})">${x.icon}<div><span>${esc(x.label)}</span><b class="mono">${esc(x.value)}</b>${x.sub ? `<i>${esc(x.sub)}</i>` : ""}</div></div>`;
  return `<div class="flowbox ${vertical ? "vertical" : ""} ${vertical && sinks.length > 3 ? "many" : ""}" role="img" aria-label="${esc(label)}">${svg}
    ${sources.map((x, i) => node(x, src[i])).join("")}
    <div class="fhouse">${icon(ICON_PATH.house, 28, "var(--use)")}<b class="mono">${esc(house)}</b><span>use</span></div>
    ${sinks.map((x, i) => node(x, snk[i])).join("")}</div>`;
}

/** The coming hours side by side: sky, temperature, rain, and what the plan expects from solar and the house in that hour. */
function hoursHtml(p) {
  const w = p && p.weather;
  const hours = (w && w.hours) || [];
  if (!hours.length) return "";
  const byHour = new Map();
  for (const q of (p.quarters || [])) {
    const k = new Date(q.t); k.setUTCMinutes(0, 0, 0);
    const e = byHour.get(k.getTime()) || { pv: 0, load: 0 };
    e.pv += q.pv || 0; e.load += q.load || 0; byHour.set(k.getTime(), e);
  }
  const m = p.meta || {};
  const slope = m.load_w_per_c;
  const why = `Solar comes from this irradiance${slope !== null && slope !== undefined ? `; house use follows the temperature (${num(-slope, 0)} W more per degree colder)` : ""}.`;
  return `<div class="card span-3"><div class="card-head"><h2>Next ${hours.length} hours</h2><span class="quiet small">used by the plan</span></div>
    <div class="hours scroll-x" role="list">${hours.map((x) => {
      const k = sky(x.code, x.is_day !== false), e = byHour.get(new Date(x.t).getTime());
      // rain only when it is likely or measured: a 10 % chance in every hour is noise
      const rain = x.precip_mm >= 0.1 ? `${num(x.precip_mm, 1)} mm` : x.precip_chance_pct >= 20 ? `${x.precip_chance_pct} %` : "";
      return `<div class="hour" role="listitem" title="${esc(k.label)}, ${num(x.cloud_pct, 0)} % cloud">
        <span class="mono small quiet">${hhmm(x.t)}</span>${icon(ICON_PATH[k.icon], 26, k.icon === "sun" ? "var(--pv)" : "currentColor")}
        <b class="mono">${x.temp_c === null || x.temp_c === undefined ? "—" : `${num(x.temp_c, 0)}°`}</b>
        <span class="small rain">${rain ? esc(rain) : "&nbsp;"}</span>
        <span class="small mono" style="color:var(--pv)">${e && e.pv > 0.005 ? `☀ ${num(e.pv, 1)}` : "&nbsp;"}</span>
        <span class="small mono" style="color:var(--use)">${e ? `⌂ ${num(e.load, 1)}` : "&nbsp;"}</span></div>`;
    }).join("")}</div>
    <p class="quiet small">${why} ☀ solar and ⌂ house in kWh per hour.</p></div>`;
}

/** Weather now and tomorrow from HEMS's own Open-Meteo fetch: sky, cloud cover, temperature and (tomorrow) rain. */
function weatherHtml(p) {
  const w = p && p.weather;
  if (!w || (!w.now && !w.tomorrow)) return `<div class="card span-2"><h2>Weather</h2><p class="quiet small">No weather yet (Open-Meteo).</p></div>`;
  const card = (title, x, big, line) => {
    if (!x) return `<div class="card wx">${icon(ICON_PATH.cloud, 44)}<div><span class="quiet small">${title}</span><b class="mono big">—</b></div></div>`;
    const k = sky(x.code, x.is_day !== false);
    return `<div class="card wx">${icon(ICON_PATH[k.icon], 44, k.icon === "sun" ? "var(--pv)" : "currentColor")}<div><span class="quiet small">${title}</span><b class="mono big">${big}</b><span class="small">${esc(k.label)} · ${line}</span></div></div>`;
  };
  const n = w.now, t = w.tomorrow;
  return card("Now", n, n && n.temp_c !== null && n.temp_c !== undefined ? `${num(n.temp_c, 0)} °C` : "—", n ? `${num(n.cloud_pct, 0)} % cloud` : "")
    + card("Tomorrow", t, t && t.temp_min_c !== null ? `${num(t.temp_min_c, 0)}–${num(t.temp_max_c, 0)} °C` : "—",
      t ? `${num(t.cloud_pct, 0)} % cloud${t.precip_mm ? ` · ${num(t.precip_mm, 1)} mm` : ""}` : "");
}

/** Expected solar for tomorrow (or the rest of today before tomorrow's prices exist) as a total and bars per hour. */
function sunHtml(p) {
  const rows = (p && p.quarters) || [];
  const tomorrow = localDayKey(Date.now() + 864e5);
  let day = rows.filter((q) => localDayKey(q.t) === tomorrow);
  const label = day.length ? "Solar tomorrow" : "Solar today";
  if (!day.length) day = rows.filter((q) => localDayKey(q.t) === localDayKey(Date.now()));
  const hours = new Map();
  for (const q of day) { const h = localHour(q.t); hours.set(h, (hours.get(h) || 0) + (q.pv || 0)); }
  const lit = [...hours].filter(([, v]) => v > 0.01);
  const total = day.reduce((a, q) => a + (q.pv || 0), 0);
  const max = Math.max(0.1, ...lit.map(([, v]) => v));
  return `<div class="card"><div class="card-head"><h2>${label}</h2><b class="mono" style="color:var(--pv)">${num(total, 1)} kWh</b></div>
    ${lit.length ? `<div class="sunbars" role="img" aria-label="${label}: ${num(total, 1)} kWh">${lit.map(([h, v]) => `<div title="${String(h).padStart(2, "0")}:00 ${num(v, 2)} kWh"><i style="height:${Math.round(v / max * 100)}%"></i><span class="mono">${String(h).padStart(2, "0")}</span></div>`).join("")}</div>` : `<p class="quiet small">No sun expected.</p>`}</div>`;
}

const LIVE_STEP_MS = 10000;            // one sample of battery and grid power every 10 s
const LIVE_SPAN_MS = 30 * 60000;       // the live charts show the last 30 minutes

/** Battery (+ charging) and grid (+ import) power in W from the role entities, null where unknown. */
function livePower(hass, s) {
  const r = (s && s.roles) || {};
  const bp = watts(hass, r.battery_power_entity);
  return { batt: bp === null ? null : bp * (r.battery_power_positive_is_discharging === false ? 1 : -1), grid: watts(hass, r.grid_entity) };
}

/**
 * One live series as a row: the label, the current value with its direction, and a sparkline of the last 30 minutes
 * around a zero line (above zero `up`, below zero `down`, each in its own colour).
 */
function sparkRow(samples, key, label, up, down) {
  const pts = samples.filter((x) => x[key] !== null);
  const now = pts.length ? pts[pts.length - 1][key] : null;
  const dir = now === null ? "" : Math.abs(now) < 50 ? "balanced" : now > 0 ? up.word : down.word;
  const W = 300, H = 56, t1 = Date.now(), t0 = t1 - LIVE_SPAN_MS;
  const max = Math.max(500, ...pts.map((x) => Math.abs(x[key])));
  const xy = (x) => `${((x.t - t0) / LIVE_SPAN_MS * W).toFixed(1)},${(H / 2 - x[key] / max * (H / 2 - 3)).toFixed(1)}`;
  const line = pts.length > 1 ? `<polyline points="${pts.map(xy).join(" ")}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke"></polyline>` : "";
  // colour above and below zero by clipping the same line twice
  const id = `clip-${key}`;
  return `<div class="spark">
    <div class="spark-head"><span>${esc(label)}</span><b class="mono" style="color:var(${now === null || Math.abs(now) < 50 ? "--fg" : now > 0 ? up.colour : down.colour})">${now === null ? "—" : kw(Math.abs(now), 2) + " kW"}</b><i>${esc(dir)}</i></div>
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(label)}, last 30 minutes">
      <defs><clipPath id="${id}-up"><rect x="0" y="0" width="${W}" height="${H / 2}"></rect></clipPath><clipPath id="${id}-dn"><rect x="0" y="${H / 2}" width="${W}" height="${H / 2}"></rect></clipPath></defs>
      <line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="var(--line)" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"></line>
      <g clip-path="url(#${id}-up)" style="color:var(${up.colour})">${line}</g><g clip-path="url(#${id}-dn)" style="color:var(${down.colour})">${line}</g>
    </svg></div>`;
}

/** The live card: battery and grid power over the last 30 minutes, 10 s per point. */
function liveChartsHtml(samples) {
  return sparkRow(samples, "batt", "Battery", { word: "charging", colour: "--charge" }, { word: "discharging", colour: "--discharge" })
    + sparkRow(samples, "grid", "Grid", { word: "import", colour: "--fg-2" }, { word: "export", colour: "--ok" })
    + `<div class="quiet small spark-axis"><span>−30 min</span><span>now · every 10 s</span></div>`;
}

/** Recorder history of one entity as [{t, w}] (W, kW converted), for filling the live charts when the panel opens. */
function historyWatts(hass, rows, entityId, sign) {
  const unit = hass.states[entityId] && hass.states[entityId].attributes.unit_of_measurement;
  return (rows || []).map((x) => ({ t: (x.lu || x.lc) * 1000, w: Number(x.s) * (unit === "kW" ? 1000 : 1) * sign })).filter((x) => Number.isFinite(x.w));
}

/* ------------------------------------------------------------------ the panel */

const VIEWS = [["overview", "Overview"], ["decisions", "Decisions"], ["insights", "Insights"]];
// earlier releases had more views and Dutch names; old bookmarks and the wall tablet URL land on the view that now holds them
const VIEW_ALIAS = {
  today: "overview", plan: "decisions", devices: "overview", nu: "overview", now: "overview", prijzen: "insights", prices: "insights", leren: "insights", learn: "insights",
  batterij: "overview", battery: "overview", auto: "overview", ev: "overview", boiler: "overview", "water-heater": "overview", net: "overview", grid: "overview",
  regie: "settings", control: "settings",
};
/** The view key for a location hash: a current key, an old alias, or null. */
function viewOf(hash) {
  const k = (hash || "").slice(1);
  const v = VIEW_ALIAS[k] || k;
  return VIEWS.some((x) => x[0] === v) || v === "settings" ? v : null;
}

class HemsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = viewOf(location.hash) || "overview";
    this._changesOnly = false;          // Decisions: only the quarters where the action changes
    this._samples = [];                 // live battery and grid power, one per 10 s, the last 30 minutes ({t, batt, grid})
    this._hours = 24;
    this._period = "day";                 // Insights: day, week, month or year
    this._sel = null;
    this._confirm = false;
    this._details = false;
    this._draft = {};                   // Settings: edited values not saved yet, by key
    this._errors = {};                  // Settings: the server's errors per key after a save
    this._undo = null;                  // Settings: the values before the last save ({section, values}), for one undo
    this._openSections = new Set(["module_battery"]);
    const q = new URLSearchParams(location.search);
    this._kiosk = q.has("kiosk");
    this._forceTheme = q.get("theme") || (this._kiosk ? "dark" : null);
    this._onHash = () => { const v = viewOf(location.hash); if (v) { this._view = v; this._render(); } };
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
  /** Add a live sample at most every 10 s and keep the last 30 minutes; the first call fills the charts from the recorder. */
  _sample(s) {
    if (!s || !s.roles) return;
    const now = Date.now();
    if (!this._seeded) { this._seeded = true; this._seedSamples(s); }
    const last = this._samples[this._samples.length - 1];
    if (last && now - last.t < LIVE_STEP_MS - 500) return;
    this._samples.push({ t: now, ...livePower(this._hass, s) });
    while (this._samples.length && this._samples[0].t < now - LIVE_SPAN_MS) this._samples.shift();
  }

  /** The last 30 minutes of battery and grid power from the recorder, resampled to 10 s steps (last value before each step). */
  async _seedSamples(s) {
    const r = s.roles, ids = [r.battery_power_entity, r.grid_entity].filter(Boolean);
    if (!ids.length) return;
    const t1 = Date.now(), t0 = t1 - LIVE_SPAN_MS;
    try {
      const res = await this._hass.callWS({ type: "history/history_during_period", start_time: new Date(t0).toISOString(), end_time: new Date(t1).toISOString(),
        entity_ids: ids, minimal_response: true, no_attributes: true, significant_changes_only: false });
      const batt = historyWatts(this._hass, res[r.battery_power_entity], r.battery_power_entity, r.battery_power_positive_is_discharging === false ? 1 : -1);
      const grid = historyWatts(this._hass, res[r.grid_entity], r.grid_entity, 1);
      const at = (rows, t) => { let v = null; for (const x of rows) { if (x.t > t) break; v = x.w; } return v; };
      const seeded = [];
      for (let t = t0; t < t1 - LIVE_STEP_MS; t += LIVE_STEP_MS) seeded.push({ t, batt: at(batt, t), grid: at(grid, t) });
      this._samples = [...seeded, ...this._samples.filter((x) => x.t >= t1 - LIVE_STEP_MS)];
    } catch (e) { /* no recorder access: the charts fill from now on */ }
    const lp = this.shadowRoot && this.shadowRoot.getElementById("live-power"); if (lp) lp.innerHTML = liveChartsHtml(this._samples);
  }

  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }
  set route(v) { this._route = v; }

  connectedCallback() {
    for (const prop of ["narrow", "panel", "route", "hass"]) upgradeProperty(this, prop);
    this.toggleAttribute("kiosk", this._kiosk);
    this._off = store.on(() => this._render());
    window.addEventListener("hashchange", this._onHash);
    window.addEventListener("resize", this._onResize);
    this._tick = setInterval(() => this._liveUpdate(), LIVE_STEP_MS);
    this._ro = new ResizeObserver(() => this._drawCharts());
    this._ro.observe(this);
  }
  disconnectedCallback() {
    if (this._off) this._off();
    window.removeEventListener("hashchange", this._onHash);
    window.removeEventListener("resize", this._onResize);
    clearInterval(this._tick);
    if (this._ro) this._ro.disconnect();
  }

  /** The flow stands upright on a phone: three columns side by side would need sideways scrolling. */
  _flowVertical() { return (this.clientWidth || window.innerWidth) < 700; }

  _go(view) { if (location.hash !== "#" + view) history.replaceState(null, "", "#" + view); this._view = view; this._sel = null; this._render(); }

  _liveUpdate() {
    // live numbers and phase bars follow every state change; the rest only a new payload
    const root = this.shadowRoot;
    if (!root || !this._hass) return;
    const p = store.payload, s = store.settings;
    const live = root.getElementById("live"); if (live) live.innerHTML = liveNumbersHtml(this._hass, p, s);
    const ph = root.getElementById("phases"); if (ph) ph.innerHTML = phasesHtml(this._hass, s);
    const fl = root.getElementById("flow"); if (fl) fl.innerHTML = flowHtml(this._hass, p, s, this._flowVertical());
    this._sample(s);
    const lp = root.getElementById("live-power"); if (lp) lp.innerHTML = liveChartsHtml(this._samples);
    const clock = root.getElementById("clock"); if (clock) clock.textContent = hhmm(Date.now());
  }

  _render() {
    if (!this._hass) return;
    // A pushed update re-renders the whole view; while a settings input has focus that would eat the user's typing, so wait for blur.
    const focused = this.shadowRoot && this.shadowRoot.activeElement;
    if (focused && /^(INPUT|SELECT)$/.test(focused.tagName) && focused.closest("[data-editor]")) { this._renderPending = true; return; }
    this._renderPending = false;
    if (this._armTimer) { clearTimeout(this._armTimer); this._armTimer = null; }      // a re-render ends a hold in progress
    const p = store.payload, s = store.settings;
    let body;
    if (store.error) body = `<section class="block"><b class="c-fault">No connection to HEMS</b><p class="quiet">${esc(store.error)}</p></section>`;
    else if (store.loaded === false) body = `<section class="block"><b>HEMS is not loaded</b><p class="quiet">The integration is off or still starting. Check Settings → Devices &amp; services → HEMS.</p></section>`;
    else if (this._kiosk) body = this._kioskView(p, s);
    else body = this[`_view_${this._view}`](p, s);
    const header = this._kiosk ? "" : `<header class="top">
        <ha-menu-button></ha-menu-button>
        <span class="title">HEMS</span>
        <nav class="tabs">${VIEWS.map(([k, label]) => `<button type="button" data-view="${k}" aria-current="${this._view === k ? "page" : "false"}">${label}</button>`).join("")}</nav>
        <span class="sp"></span>
        ${pillHtml(p)}
        <button type="button" class="gear" data-view="settings" aria-label="Control and settings" aria-current="${this._view === "settings" ? "page" : "false"}">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="12" r="3"></circle><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"></path></svg>
        </button>
      </header>
      ${this._details ? `<div class="details">${healthHtml(p, store)}</div>` : ""}`;
    this.shadowRoot.innerHTML = `<style>${BASE_CSS}${PANEL_CSS}</style>${header}${alertsHtml(p)}<main>${body}</main>`;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) { menu.hass = this._hass; menu.narrow = this._narrow; }
    this.shadowRoot.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => this._go(b.dataset.view)));
    this.shadowRoot.querySelectorAll("[data-hours]").forEach((b) => b.addEventListener("click", () => { this._hours = Number(b.dataset.hours); this._sel = null; this._render(); }));
    this.shadowRoot.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => { this._changesOnly = b.dataset.filter === "changes"; this._render(); }));
    this.shadowRoot.querySelectorAll("[data-period]").forEach((b) => b.addEventListener("click", () => { this._period = b.dataset.period; this._render(); }));
    this._bindActions();
    this._bindEditor();
    this._drawCharts();
  }

  _drawCharts() {
    if (!this.shadowRoot || !store.payload) return;
    const p = store.payload;
    const combined = this.shadowRoot.getElementById("combined");
    if (combined) drawCombined(this, combined, p, this._kiosk ? 24 : this._hours, this._kiosk);
    const hm = this.shadowRoot.getElementById("heat"); if (hm) drawHeatmap(this, hm, p);
    const dz = this.shadowRoot.getElementById("days"); if (dz) drawDays(this, dz, p, this._period);
    const svg = this.shadowRoot.getElementById("tl");
    if (!svg) return;
    drawTimeline(this, svg, p, {
      hours: this._hours, lanes: ["price", "plan", "soc", "pvload", "devices"], compact: this.clientWidth < 600, selected: this._sel,
      onSelect: (i) => {
        this._sel = i;
        const why = this.shadowRoot.getElementById("why");
        if (why) why.innerHTML = whyHtml(store.payload, i);
        this._drawCharts();
      },
    });
  }

  _hoursSeg() {
    return `<span class="seg small">${[8, 24, 48].map((h) => `<button type="button" data-hours="${h}" aria-pressed="${this._hours === h}">${h} h</button>`).join("")}</span>`;
  }

  /* ---------------- Overview: everything on one screen */
  _view_overview(p, s) {
    const h = headline(p);
    const d = p && p.decision;
    return `
      <section class="hero">
        <div class="say">
          <span class="quiet">Now · ${hhmm(Date.now())}</span>
          <h1>${esc(h.lead)}</h1>
          ${h.rest ? `<p class="next">${h.rest}</p>` : ""}
          <p class="why">${h.why}</p>
        </div>
        <div class="card money">
          <span class="quiet small">vs. self-consumption only</span>
          ${this._moneyRows(p, d)}
        </div>
      </section>
      ${recsHtml(p, this._applyId)}
      <section class="grid-3">
        <div class="card span-2"><div class="card-head"><h2>Energy flow</h2><span class="quiet small">live</span></div><div id="flow">${flowHtml(this._hass, p, s, this._flowVertical())}</div></div>
        <div class="card"><div class="card-head"><h2>Live power</h2><span class="quiet small">30 min</span></div><div id="live-power">${liveChartsHtml(this._samples)}</div>
          <div class="card-head" style="margin-top:18px"><h2>Phases</h2><span class="quiet small">max ${num((s && s.options && s.options.grid_limit_a) || 25, 0)} A</span></div><div id="phases">${phasesHtml(this._hass, s)}</div></div>
      </section>
      <section class="grid-3">${weatherHtml(p)}${sunHtml(p)}${hoursHtml(p)}</section>
      <section class="block chart">
        <div class="chart-head">
          <h2>Next ${this._hours} hours</h2><span class="quiet">per quarter</span>
          <span class="key"><i class="sw" style="background:var(--mid-bar)"></i>price</span>
          <span class="key"><i class="ln"></i>battery %</span>
          <span class="key"><i class="sw" style="background:var(--charge)"></i>charge</span>
          <span class="key"><i class="sw" style="background:var(--discharge)"></i>sell</span>
          <span class="sp"></span>${this._hoursSeg()}
        </div>
        <svg id="combined" style="display:block;width:100%"></svg>
      </section>
      <section class="grid-2">
        <div class="card"><h2>Coming up</h2>${agendaHtml(p)}</div>
        <div class="card"><h2>Devices</h2>${this._devicesHtml(p, s)}</div>
      </section>`;
  }

  /** One compact row per module: what it does now and its mode; the EV keeps its force-charge override. */
  _devicesHtml(p, s) {
    const o = (s && s.options) || {};
    const r = (s && s.roles) || {};
    const b = (p && p.battery) || {};
    const soc = stateNum(this._hass, r.soc_entity);
    const rows = [];
    rows.push(`<div class="dev"><span class="dev-name">${ICON.battery}Battery</span>
      <div class="meter"><i style="width:${soc ?? 0}%"></i><em style="left:${b.capacity_kwh ? b.reserve_kwh / b.capacity_kwh * 100 : 0}%"></em></div>
      <span class="mono">${soc === null ? "—" : num(soc, 0) + " %"}</span>${modeSegHtml(p, "battery")}</div>`);
    if (o.ev_enabled) {
      const ev = p && p.ev;
      const forceOn = this._hass.states["switch.hems_ev_force_charge"] && this._hass.states["switch.hems_ev_force_charge"].state === "on";
      const status = ev ? (EV_LABEL[ev.status] || ev.status) : "no plan yet";
      rows.push(`<div class="dev"><span class="dev-name">${ICON.car}EV</span><span class="quiet small">${esc(status)}${ev && ev.shortfall_kwh > 0 ? ` · <span class="c-fault">${num(ev.shortfall_kwh, 1)} kWh short</span>` : ""}</span><span></span>${modeSegHtml(p, "ev")}</div>
        <div class="dev-ctl">${this._confirm ? `<span class="small">${forceOn ? "Stop force charging?" : "Start force charging? Only the plan changes in dry-run."}</span>
          <button type="button" class="btn pri" data-act="force-yes">${forceOn ? "Stop" : "Start"}</button><button type="button" class="btn" data-act="force-no">Cancel</button>`
          : `<button type="button" class="btn" data-act="force">${forceOn ? "Force charging · stop…" : "Force charge…"}</button>`}</div>`);
    }
    if (o.water_heater_enabled) {
      const wh = r.water_heater_entity && this._hass.states[r.water_heater_entity];
      const temp = wh ? (wh.attributes.current_temperature ?? null) : null;
      const next = ((p && p.heating) || [])[0];
      rows.push(`<div class="dev"><span class="dev-name">${ICON.tank}Water heater</span><span class="quiet small">${temp === null ? "" : num(temp, 0) + " °C · "}${next ? esc(span(next.from, next.to)) : "no run planned"}</span><span></span>${modeSegHtml(p, "water_heater")}</div>`);
    }
    if (o.spa_enabled) {
      const spa = r.spa_climate_entity && this._hass.states[r.spa_climate_entity];
      const t = spa ? spa.attributes.current_temperature : null;
      rows.push(`<div class="dev"><span class="dev-name">${ICON.spa}Spa</span><span class="quiet small">${t === null || t === undefined ? "no climate entity" : num(t, 1) + " °C"}</span><span></span><span></span></div>`);
    }
    return `<div class="devs">${rows.join("")}</div>`;
  }

  /* ---------------- Decisions: every planned quarter and the comparison behind it */
  _view_decisions(p) {
    const b = (p && p.battery) || {};
    const rows = ((p && p.quarters) || []).filter((q) => q.act);
    const shown = this._changesOnly ? rows.filter((q, i) => i === 0 || q.act !== rows[i - 1].act) : rows;
    const pct = (kwh) => b.capacity_kwh ? num(kwh / b.capacity_kwh * 100, 0) + " %" : "—";
    const vals = rows.flatMap((q) => [q.sell, q.keep, q.buy]).filter((v) => v !== null && v !== undefined);
    const lo = vals.length ? Math.min(...vals) : 0, hi = vals.length ? Math.max(...vals) : 1;
    const bar = (v, c) => v === null || v === undefined ? `<i class="vb"></i>` : `<i class="vb"><i style="width:${Math.max(3, (v - lo) / (hi - lo || 1) * 100)}%;background:var(${c})"></i></i>`;
    return `
      <section class="say"><span class="quiet">Per kWh: sell, keep or buy. The best wins.</span><h1 class="mid">${esc((p && p.decision && p.decision.plan_text) || "—")}</h1></section>
      <section class="chips">
        <span class="chip">Margin <b class="mono">€ ${num(b.min_profit_margin, 2)}</b></span>
        <span class="chip">Efficiency <b class="mono">${num((b.round_trip_eff || 0) * 100, 0)} %</b></span>
        <span class="chip">Sell floor <b class="mono">${b.capacity_kwh ? num(b.reserve_kwh / b.capacity_kwh * 100, 0) : "—"} %</b></span>
        <span class="chip">Changed <b class="mono">${p && p.diff && p.diff.available ? p.diff.changed : "—"}</b> quarters</span>
      </section>
      <section class="block">
        <div class="chart-head"><h2>Timeline</h2><span class="sp"></span>${this._hoursSeg()}</div>
        <svg id="tl" style="display:block;width:100%"></svg>
        <div class="why-box" id="why">${whyHtml(p, this._sel)}</div>
      </section>
      <section class="block">
        <div class="chart-head"><h2>Every quarter</h2><span class="sp"></span>
          <span class="seg small" role="group" aria-label="Filter"><button type="button" data-filter="all" aria-pressed="${!this._changesOnly}">All</button><button type="button" data-filter="changes" aria-pressed="${!!this._changesOnly}">Changes</button></span></div>
        <div class="scroll-x"><table class="dec">
          <tr><th>Time</th><th>Action</th><th>Battery</th><th>Why</th><th>Sell · keep · buy</th></tr>
          ${shown.map((q) => `<tr><td class="mono">${esc(dayWord(q.t) === "today" ? "" : dayWord(q.t) + " ")}${hhmm(q.t)}</td>
            <td><span class="act act-${q.act}">${esc(ACTION_LABEL[q.act] || q.act)}</span></td>
            <td class="n">${q.soc === null ? "—" : pct(q.soc)}</td>
            <td class="small">${esc(q.why || "")}</td>
            <td><div class="vbars">${bar(q.sell, "--discharge")}${bar(q.keep, "--fg-2")}${bar(q.buy, "--charge")}</div><span class="mono quiet small">${eur(q.sell, 3)} · ${eur(q.keep, 3)} · ${eur(q.buy, 3)}</span></td></tr>`).join("")}
        </table></div>
      </section>
      <section class="grid-2">
        <div class="card"><h2>Changes since the last plan</h2>${diffHtml(p)}</div>
        <div class="card"><h2>Windows</h2><div class="scroll-x">${windowsTable(p)}</div></div>
      </section>
      <details class="block"><summary>Battery detail</summary><div class="stack" style="margin-top:12px">${verdictHtml(p, 24)}${chainHtml(p)}<div class="scroll-x">${sellTable(p)}</div>${wouldWriteHtml(p && p.saj)}</div></details>`;
  }

  _moneyRows(p, d) {
    const r = p && p.realised, t = r && r.today;
    const signed = (v) => v === null || v === undefined ? "—" : (v > 0 ? "+ " : v < 0 ? "− " : "") + "€ " + num(Math.abs(v), 2);
    return `<div class="rows">
      <div><span>Saved today</span><span class="mono" style="color:var(${t && t.gain >= 0 ? "--ok" : "--fault"})">${t && t.quarters ? signed(t.gain) : "—"}</span></div>
      <div><span>Energy cost today</span><span class="mono">${t && t.quarters ? "€ " + num(t.cost, 2) : "—"}</span></div>
      <div><span>Plan, next 48 h</span><span class="mono">${d ? signed(d.expected_saving) : "—"}</span></div>
    </div>`;
  }

  /* ---------------- Insights */
  _view_insights(p) {
    const r = p && p.realised;
    const err = (r && r.errors) || {};
    const st = p ? priceStats(p.quarters || []) : {};
    const cheap = p ? cheapestBlock(p.quarters || [], 12) : null;
    const signed = (v) => v === null || v === undefined ? "—" : (v > 0 ? "+ " : v < 0 ? "− " : "") + "€ " + num(Math.abs(v), 2);
    const qs = ((r && r.quarters) || []).slice(-96);
    const withOther = qs.filter((q) => q.other && q.planned);
    const agree = withOther.filter((q) => otherAction(q.other) === q.planned).length;
    const buckets = periodBuckets((r && r.daily) || [], this._period);
    const current = buckets[buckets.length - 1];
    const rest = r && r.rest_of_day;
    const dryRun = !p || !p.control || (p.control.modes || {}).battery !== "advisory";
    const errRow = (e, label) => `<div><span>${label}</span><span class="mono">${e ? num(e.mae_kwh_day, 2) + " kWh/day" : "—"}</span></div>`;
    return `
      <section class="hero">
        <div class="say">
          <div class="row"><span class="quiet">${dryRun ? "Battery as it ran" : "HEMS"} vs self-consumption, ${PERIOD_NOW[this._period]}</span><span class="sp"></span>${this._periodSeg()}</div>
          <h1 class="money" style="color:var(${current && current.gain >= 0 ? "--ok" : "--fault"})">${current ? signed(current.gain) : "—"}</h1>
          ${current ? `<p class="small">${current.gain >= 0 ? "Better" : "Worse"} than a battery on self-consumption only${current.today ? " so far" : ""}.</p>` : ""}
          ${this._period === "day" && rest ? `<p class="small">Rest of today, if the HEMS plan runs: <b class="mono">${signed(rest.gain)}</b> · end of day <b class="mono" style="color:var(${rest.end_of_day >= 0 ? "--ok" : "--fault"})">${signed(rest.end_of_day)}</b></p>` : ""}
          <p class="why">Compared with the battery on self-consumption only${r && r.since ? `; ${signed(r.gain_total)} since ${esc(dayShort(r.since))}` : ""}.
            Energy stored above that is valued at the day's average import price.${dryRun ? " In dry run the old battery manager controls the battery, so this is its result, not HEMS's." : ""}</p>
          ${current ? `<p class="quiet small">Imported ${num(current.import_kwh, 1)} kWh · exported ${num(current.export_kwh, 1)} kWh · solar ${num(current.pv_kwh, 1)} kWh · house ${num(current.load_kwh, 1)} kWh</p>` : ""}
        </div>
        <svg id="days" style="display:block;flex:1 1 420px;min-width:0"></svg>
      </section>
      <section class="three">
        <div class="block"><h2>Forecasts</h2><div class="rows">${errRow(err.pv, "Solar off by")}${errRow(err.load, "House off by")}</div>
          ${err.pv || err.load ? "" : `<p class="quiet small">Needs a few days of measurements.</p>`}</div>
        <div class="block"><h2>Prices</h2><div class="rows">
          <div><span>Today average</span><span class="mono">${eur(st.avg, 3)}</span></div>
          <div><span>Cheapest 3 h</span><span class="mono c-charge">${cheap ? esc(span(cheap.from, cheap.to)) : "—"}</span></div>
          <div><span>Highest</span><span class="mono c-discharge">${eur(st.max, 3)}</span></div></div>
          <p class="quiet small">Net metering ends ${esc((store.settings && store.settings.options && store.settings.options.salderen_until) || "2027-01-01")}.</p></div>
        <div class="block"><h2>Old battery manager</h2><div class="rows">
          <div><span>Agrees</span><span class="mono">${withOther.length ? `${agree} of ${withOther.length}` : "—"}</span></div></div>
          ${withOther.length ? "" : `<p class="quiet small">Fills per quarter once its action sensor is assigned.</p>`}</div>
      </section>
      <details class="block"><summary>Prices</summary><div class="scroll-x" style="margin-top:12px"><svg id="heat" style="display:block;min-width:620px;width:100%"></svg></div></details>
      <details class="block"><summary>Last 24 hours</summary><div style="margin-top:12px">${this._quarterTable(qs)}</div></details>`;
  }

  _periodSeg() {
    return `<span class="seg small">${PERIODS.map((k) => `<button type="button" data-period="${k}" aria-pressed="${this._period === k}">${PERIOD_LABEL[k]}</button>`).join("")}</span>`;
  }

  _quarterTable(qs) {
    if (!qs.length) return `<p class="quiet">No measured quarters yet.</p>`;
    const actual = (q) => q.battery_kwh > 0.05 ? "charge" : q.battery_kwh < -0.05 ? "discharge" : "idle";
    const hasOther = qs.some((q) => q.other);
    return `<div class="scroll-x"><table><tr><th>Quarter</th><th>HEMS would</th>${hasOther ? "<th>Old manager</th>" : ""}<th>Battery did</th><th>Grid</th><th>Solar</th><th>House</th><th>Cost</th><th>Self-cons.</th></tr>
      ${qs.slice().reverse().map((q) => { const off = hasOther && q.other && q.planned && otherAction(q.other) !== q.planned;
        return `<tr class="${off ? "off" : ""}"><td class="mono">${hhmm(q.t)}</td><td class="c-${q.planned || "idle"}">${esc(ACTION_LABEL[q.planned] || q.planned || "—")}</td>
        ${hasOther ? `<td>${esc(q.other || "—")}</td>` : ""}<td class="c-${actual(q)}">${ACTION_LABEL[actual(q)]} ${num(q.battery_kwh * 4, 1)} kW</td>
        <td class="n">${num((q.import_kwh - q.export_kwh) * 4, 1)} kW</td><td class="n">${num(q.pv_kwh * 4, 1)}${q.fc_pv_kwh !== null && q.fc_pv_kwh !== undefined ? ` <span class="quiet">(${num(q.fc_pv_kwh * 4, 1)})</span>` : ""}</td>
        <td class="n">${num(q.load_kwh * 4, 1)}${q.fc_load_kwh !== null && q.fc_load_kwh !== undefined ? ` <span class="quiet">(${num(q.fc_load_kwh * 4, 1)})</span>` : ""}</td>
        <td class="n">${q.cost === undefined ? "—" : "€ " + num(q.cost, 3)}</td><td class="n">${q.baseline_cost === undefined ? "—" : "€ " + num(q.baseline_cost, 3)}</td></tr>`; }).join("")}
      </table></div><p class="quiet small">In brackets: what HEMS expected. Quarters with less than 60 % measured time do not count in the totals.</p>`;
  }

  /* ---------------- Settings (behind the gear) */
  _view_settings(p, s) {
    if (!s) return `<p class="quiet">Loading settings…</p>`;
    const c = (p && p.control) || { modes: {}, armed: false };
    return `
      <section class="block stack">
        <h2>Control</h2>
        <div class="row"><span class="tag ${c.armed ? "fault" : "ok"}">${c.armed ? "ARMED" : "SAFE"}</span>
          <button type="button" class="btn ${c.armed ? "" : "pri"} hold" data-act="arm">${c.armed ? "Disarm" : "Hold 1.5 s to arm"}</button>
          <button type="button" class="btn" data-act="disarm">All to dry-run</button></div>
        <p class="quiet small">No module writes to a device yet; arming changes nothing now, but it is logged. After a restart the master switch is always off. Per-device modes are on Devices.</p>
      </section>
      <section class="block stack">
        <h2>Energy dashboard</h2>
        <p class="quiet small">Adds HEMS's solar and battery counters and its import and export price to Home Assistant's Energy dashboard where they are missing. Nothing you set is removed or replaced.</p>
        <div class="row"><button type="button" class="btn" data-act="energy-preview">Check</button>${this._energy && this._energy.changes.length && this._energy.preview ? `<button type="button" class="btn pri" data-act="energy-apply">Add ${this._energy.changes.length}</button>` : ""}</div>
        ${this._energy ? `<p class="quiet small">${this._energy.changes.length ? (this._energy.saved ? "Added: " : "Would add: ") + this._energy.changes.map(esc).join(" · ") : "Nothing missing: the Energy dashboard already has solar, battery and prices."}</p>` : ""}
      </section>
      ${this._editorHtml(s)}
      <section class="block stack">
        <div class="spread"><h2>Installation and contract</h2>${configureLink(s)}</div>
        <p class="quiet small">These are set in Home Assistant (Settings → Devices &amp; services → HEMS → Configure).</p>
        ${settingsInWords(s.options).map(([h, t]) => `<div><b>${h}</b><p class="quiet small" style="margin:2px 0 0">${t}</p></div>`).join("")}
      </section>
      <details class="block"><summary>Entities</summary><div class="scroll-x" style="margin-top:12px"><table>
        ${Object.entries(s.roles).sort().map(([k, v]) => `<tr><td class="mono">${esc(k.replace(/_entity$|_entities$/, ""))}</td><td class="mono">${esc(Array.isArray(v) ? v.join(", ") : String(v))}</td><td class="mono small">${typeof v === "string" && v.includes(".") ? (this._hass.states[v] ? esc(this._hass.states[v].state) : `<span class="c-fault">missing</span>`) : ""}</td></tr>`).join("")}
      </table></div></details>
      <p class="quiet small mono">panel ${VERSION} · HEMS build ${esc((p && p.meta.build) || "?")}</p>`;
  }

  /* ---------------- Settings editor: the planning settings (hems/settings/update); the installation stays in Home Assistant */
  _value(s, key) { return key in this._draft ? this._draft[key] : s.options[key]; }

  _editorHtml(s) {
    if (!s.editable) return "";
    const admin = !!(this._hass.user && this._hass.user.is_admin);
    return `<section class="block stack" data-editor>
        <div class="spread"><h2>Planning</h2>${this._undo ? `<button type="button" class="btn" data-undo>Undo last save</button>` : ""}</div>
        <p class="quiet small">Changes apply at once: HEMS replans as soon as you save.${admin ? "" : " Only an administrator can change them."}</p>
        ${s.editable.map((part) => this._sectionHtml(s, part, admin)).join("")}
      </section>`;
  }

  _sectionHtml(s, part, admin) {
    const name = part.section;
    const keys = part.settings.map((x) => x.key);
    const dirty = keys.filter((k) => k in this._draft && this._draft[k] !== s.options[k]);
    const title = ((s.labels && s.labels.sections[name]) || name).replace(/^(Module|Base): /, "");
    const plain = part.settings.filter((x) => !(name === "module_ev" && x.kind === "time") && !/^reserve_soc_[a-z]+day_pct$/.test(x.key));
    return `<details class="setsec" data-section="${name}" ${this._openSections.has(name) ? "open" : ""}>
        <summary><span>${esc(title)}</span>${dirty.length ? `<span class="tag warn">${dirty.length} unsaved</span>` : ""}</summary>
        ${name === "module_battery" ? socBarHtml(s, (k) => this._value(s, k)) + learnedHtml(s) : ""}
        <div class="setgrid">${plain.map((x) => this._inputHtml(s, x, admin)).join("")}</div>
        ${name === "module_battery" ? this._weekHtml(s, "reserve_soc_%s_pct", "number", "Sell floor minimum per weekday (%; 0 = the general minimum)", admin) : ""}
        ${name === "module_ev" ? this._weekHtml(s, "ev_deadline_%s", "time", "Deadline per weekday (empty = no deadline that day)", admin) : ""}
        <div class="row"><button type="button" class="btn pri" data-save="${name}" ${dirty.length && admin ? "" : "disabled"}>Save</button>
          ${dirty.length ? `<button type="button" class="btn" data-reset="${name}">Discard</button>` : ""}</div>
      </details>`;
  }

  _inputHtml(s, x, admin) {
    const label = (s.labels && s.labels.settings[x.key]) || x.key;
    const v = this._value(s, x.key);
    const err = this._errors[x.key];
    const dis = admin ? "" : "disabled";
    let input;
    if (x.kind === "bool") input = `<input type="checkbox" data-key="${x.key}" ${v ? "checked" : ""} ${dis}>`;
    else if (x.kind === "choice") input = `<select data-key="${x.key}" ${dis}>${x.options.map((o) => `<option value="${esc(o)}" ${o === v ? "selected" : ""}>${esc(DAY_LABEL[o] || o)}</option>`).join("")}</select>`;
    else if (x.kind === "number") input = `<input type="number" data-key="${x.key}" value="${esc(v)}" min="${x.min}" max="${x.max}" step="${x.step < 0.001 ? "any" : x.step}" ${dis}>`;
    else input = `<input type="${x.kind === "time" ? "time" : "text"}" data-key="${x.key}" value="${esc(v)}" ${dis}>`;
    return `<label class="setfield ${x.kind === "bool" ? "inline" : ""} ${err ? "bad" : ""}"><span>${esc(label)}</span>${input}${err ? `<em class="c-fault small">${esc(err)}</em>` : ""}</label>`;
  }

  _weekHtml(s, pattern, kind, title, admin) {
    const days = Object.keys(DAY_LABEL);
    return `<div class="week"><span class="quiet small">${esc(title)}</span><div class="weekgrid">${days.map((d) => {
      const key = pattern.replace("%s", d);
      const spec = s.editable.flatMap((p) => p.settings).find((x) => x.key === key) || { key, kind };
      const v = this._value(s, key);
      const err = this._errors[key];
      const input = kind === "time" ? `<input type="time" data-key="${key}" value="${esc(v)}" ${admin ? "" : "disabled"}>`
        : `<input type="number" data-key="${key}" value="${esc(v)}" min="${spec.min}" max="${spec.max}" step="${spec.step}" ${admin ? "" : "disabled"}>`;
      return `<label class="setfield ${err ? "bad" : ""}"><span>${DAY_LABEL[d].slice(0, 3)}</span>${input}${err ? `<em class="c-fault small">${esc(err)}</em>` : ""}</label>`;
    }).join("")}</div></div>`;
  }

  _bindEditor() {
    const root = this.shadowRoot;
    const s = store.settings;
    if (!s || !root.querySelector("[data-editor]")) return;
    const read = (el) => {
      const spec = s.editable.flatMap((p) => p.settings).find((x) => x.key === el.dataset.key);
      if (el.type === "checkbox") return el.checked;
      if (spec && spec.kind === "number") return el.value === "" ? null : Number(el.value);
      return el.value;
    };
    root.querySelectorAll("[data-editor] [data-key]").forEach((el) => {
      const keep = () => {
        this._draft[el.dataset.key] = read(el); delete this._errors[el.dataset.key];
        // the Save button follows the draft at once; a full re-render waits until focus leaves the editor
        const sec = el.closest("details.setsec"), btn = sec && sec.querySelector("[data-save]");
        if (btn && this._hass.user && this._hass.user.is_admin) btn.disabled = !this._sectionKeys(sec.dataset.section).some((k) => k in this._draft && this._draft[k] !== s.options[k]);
      };
      el.addEventListener("input", keep);
      el.addEventListener("change", () => { keep(); if (el.type === "checkbox" || el.tagName === "SELECT") this._render(); });
    });
    // after typing: the deferred pushed update and the dirty counts catch up once focus leaves the editor
    root.querySelector("[data-editor]").addEventListener("focusout", (ev) => {
      // moving to another field or a button of the editor is not leaving it (a re-render now would swallow a click on Save)
      if (ev.relatedTarget && ev.relatedTarget.closest && ev.relatedTarget.closest("[data-editor]")) return;
      setTimeout(() => this._render(), 0);
    });
    root.querySelectorAll("details.setsec").forEach((d) => d.addEventListener("toggle", () => {
      if (d.open) this._openSections.add(d.dataset.section); else this._openSections.delete(d.dataset.section);
    }));
    root.querySelectorAll("[data-save]").forEach((b) => b.addEventListener("click", () => this._saveSection(b.dataset.save)));
    root.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", () => {
      for (const k of this._sectionKeys(b.dataset.reset)) { delete this._draft[k]; delete this._errors[k]; }
      this._render();
    }));
    const undo = root.querySelector("[data-undo]");
    if (undo) undo.addEventListener("click", () => this._send(this._undo.section, this._undo.values, false));
  }

  _sectionKeys(name) {
    const part = (store.settings.editable || []).find((p) => p.section === name);
    return part ? part.settings.map((x) => x.key) : [];
  }

  _saveSection(name) {
    const o = store.settings.options;
    const changes = {};
    for (const k of this._sectionKeys(name)) if (k in this._draft && this._draft[k] !== o[k]) changes[k] = this._draft[k];
    if (Object.keys(changes).length) this._send(name, changes, true);
  }

  /** Store changes; `keepUndo` remembers the old values so one undo can put them back. */
  async _send(name, changes, keepUndo) {
    const o = store.settings.options;
    const before = Object.fromEntries(Object.keys(changes).map((k) => [k, o[k]]));
    try {
      const res = await this._hass.callWS({ type: "hems/settings/update", changes });
      if (!res.ok) { this._errors = { ...this._errors, ...res.errors }; this._render(); return; }
      for (const k of Object.keys(changes)) { delete this._draft[k]; delete this._errors[k]; }
      store.settings = { ...store.settings, options: res.options };
      this._undo = keepUndo ? { section: name, values: before } : null;
      store.refreshSettings(this._hass);
    } catch (err) {
      this._errors = { ...this._errors, ...Object.fromEntries(Object.keys(changes).map((k) => [k, (err && err.message) || "not saved"])) };
    }
    this._render();
  }

  /* ---------------- Wall tablet: one screen, read from across the room */
  _kioskView(p, s) {
    const h = headline(p);
    const next = agenda(p).find((x) => !x.what.startsWith("Battery"));
    const bad = problems(p);
    return `<div class="kiosk">
      <div class="spread quiet"><span id="clock">${hhmm(Date.now())}</span><span class="row" style="gap:8px"><i class="dot" style="background:var(${bad.length ? "--warn" : "--ok"})"></i>${bad.length ? esc(bad.join(", ")) : "Dry-run"}</span></div>
      <section class="hero">
        <div class="say"><h1 class="huge">${esc(h.lead.replace(/ the battery\.$/, "").replace(/\.$/, ""))}</h1><p class="why big">${h.rest}</p></div>
        <div id="live">${liveNumbersHtml(this._hass, p, s)}</div>
      </section>
      <section class="block chart"><svg id="combined" style="display:block;width:100%"></svg></section>
      <p class="why big">${next ? `Next: ${esc(next.what.split(" · ")[0].toLowerCase())} ${esc(span(next.from, next.to))}` : ""}${p && p.ev ? `${next ? " · " : ""}${evLine(p)}` : ""}</p>
    </div>`;
  }

  _bindActions() {
    const root = this.shadowRoot;
    const on = (sel, fn) => { const b = root.querySelector(sel); if (b) b.addEventListener("click", fn); };
    on('[data-act="details"]', () => { this._details = !this._details; this._render(); });
    root.querySelectorAll('[data-act="disarm"]').forEach((b) => b.addEventListener("click", () => this._hass.callService("hems", "disarm_all", {})));
    // Energy dashboard setup: first a preview, then the owner adds what it lists
    const energy = async (preview) => {
      const res = await this._hass.callService("hems", "setup_energy_dashboard", { preview }, undefined, true, true);
      this._energy = res && res.response; this._render();
    };
    on('[data-act="energy-preview"]', () => energy(true));
    on('[data-act="energy-apply"]', () => energy(false));
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

/* calm: few borders, surfaces by a slightly lighter ground, one text size per role, colour only for meaning */
const PANEL_CSS = `
:host { min-height:100vh; font-size:15px; }
header.top { display:flex; align-items:center; gap:28px; padding:0 32px; height:64px; background:var(--bg); border-bottom:1px solid var(--line-2); position:sticky; top:0; z-index:2; }
header .title { font:600 18px var(--font-body); letter-spacing:.02em; }
nav.tabs { display:flex; gap:24px; overflow-x:auto; scrollbar-width:none; min-width:0; }
nav.tabs button { border:none; background:none; padding:21px 0; font:15px var(--font-body); color:var(--fg-3); cursor:pointer; white-space:nowrap; box-shadow:none; }
nav.tabs button[aria-current="page"] { color:var(--fg); box-shadow:inset 0 -2px 0 var(--fg); }
.sp { flex:1; }
.pill { display:inline-flex; align-items:center; gap:8px; background:none; border:1px solid var(--line); border-radius:999px; padding:8px 14px; color:var(--fg-2); font:13px var(--font-body); min-height:40px; cursor:pointer; max-width:420px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pill.bad { border-color:var(--warn); color:var(--fg); }
.gear { width:44px; height:44px; border-radius:10px; border:1px solid var(--line); background:none; color:var(--fg-2); display:flex; align-items:center; justify-content:center; cursor:pointer; flex:none; }
.gear[aria-current="page"] { color:var(--fg); border-color:var(--fg-3); }
.details { padding:10px 32px; border-bottom:1px solid var(--line-2); }
main { padding:36px 32px 48px; max-width:1360px; margin:0 auto; display:flex; flex-direction:column; gap:36px; }
h1 { margin:0; font:500 34px/1.2 var(--font-body); letter-spacing:-.01em; }
h1.mid { font-size:24px; }
h1.money { font:500 44px var(--font-data); }
h2 { margin:0 0 10px; font:500 15px var(--font-body); color:var(--fg); }
p { margin:0; }
.quiet { color:var(--fg-3); }
.fg { color:var(--fg); font-weight:500; }
.small { font-size:13px; }
.why { color:var(--fg-2); font-size:15px; max-width:68ch; }
.c-fault { color:var(--fault); }
.hero { display:flex; flex-wrap:wrap; align-items:flex-end; gap:32px 48px; }
.say { display:flex; flex-direction:column; gap:10px; min-width:0; }
.hero .say { flex:999 1 420px; }   /* only beside the live numbers: in the page column a basis would become a height */
.live { margin:0; display:grid; grid-template-columns:repeat(3,minmax(96px,auto)); gap:32px; }
.live dt { font-size:13px; color:var(--fg-3); }
.live dd { margin:4px 0 0; font:500 26px var(--font-data); white-space:nowrap; }
.live dd small { font-size:14px; color:var(--fg-3); }
.live .sub { font-size:12px; color:var(--fg-3); white-space:nowrap; }
.block { background:var(--panel); border-radius:14px; padding:22px 24px; min-width:0; }
.setsec { border-top:1px solid var(--line-2); padding:12px 0; }
.setsec > summary { display:flex; align-items:center; gap:10px; cursor:pointer; font-weight:500; min-height:36px; }
.setsec[open] > summary { margin-bottom:12px; }
.setgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px 20px; margin-bottom:14px; }
.setfield { display:flex; flex-direction:column; gap:4px; font-size:13px; color:var(--fg-2); min-width:0; }
.setfield.inline { flex-direction:row-reverse; justify-content:flex-end; align-items:center; gap:10px; }
.setfield input:not([type=checkbox]), .setfield select { font:14px var(--font-data); padding:8px 10px; min-height:40px; border-radius:8px; border:1px solid var(--line); background:var(--panel-2); color:var(--fg); width:100%; }
.setfield input[type=checkbox] { width:20px; height:20px; }
.setfield.bad input, .setfield.bad select { border-color:var(--fault); }
.week { display:flex; flex-direction:column; gap:6px; margin-bottom:14px; }
.weekgrid { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:8px; }
@media (max-width:640px) { .weekgrid { grid-template-columns:repeat(4,minmax(0,1fr)); } }
.socbar { position:relative; height:14px; border-radius:7px; background:var(--panel-2); overflow:hidden; margin:4px 0 6px; }
.socbar i { position:absolute; top:0; bottom:0; }
.socbar .floor { left:0; background:var(--fault); opacity:.55; }
.socbar .band { background:var(--discharge-soft); border-left:2px solid var(--discharge); border-right:2px solid var(--discharge); }
.socbar .ceil { background:var(--line); }
.learned { margin:10px 0 14px; display:flex; flex-direction:column; gap:2px; }
.block.chart { padding:20px 24px 14px; }
.chart-head { display:flex; align-items:center; flex-wrap:wrap; gap:10px 20px; margin-bottom:12px; font-size:13px; color:var(--fg-3); }
.chart-head h2 { margin:0; }
.key { display:inline-flex; align-items:center; gap:6px; }
.key .sw { width:10px; height:10px; border-radius:2px; display:inline-block; }
.key .ln { width:14px; height:2px; background:var(--fg); display:inline-block; }
.seg.small button { min-height:34px; padding:6px 10px; }
.two { display:grid; grid-template-columns:minmax(0,2fr) minmax(0,1fr); gap:40px; }
.three { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr)); gap:20px; }
.agenda { display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:0 20px; }
.agenda > span { padding:13px 0; border-top:1px solid var(--line-2); }
.rows > div { display:flex; justify-content:space-between; gap:12px; padding:13px 0; border-top:1px solid var(--line-2); }
.rows > div > span:first-child { color:var(--fg-2); }
.rows + .small, .rows + a { display:inline-block; margin-top:8px; }
.device { background:var(--panel); border-radius:14px; padding:24px 28px; display:grid; grid-template-columns:200px minmax(0,1fr) 250px; gap:20px 36px; align-items:start; }
.device.thin { background:none; padding:4px 28px; grid-template-columns:200px minmax(0,1fr); align-items:center; }
.device.risk { box-shadow:inset 0 0 0 1px var(--fault); }
.device .name { display:flex; flex-direction:column; gap:6px; }
.device .name h2 { margin:0; font-size:19px; }
.device .body { display:flex; flex-direction:column; gap:14px; min-width:0; }
.device .body > p { font-size:17px; }
.device .ctl { display:flex; flex-direction:column; gap:10px; align-items:flex-start; }
.meter { height:12px; border-radius:6px; background:var(--panel-2); position:relative; overflow:hidden; }
.meter i { position:absolute; inset:0 auto 0 0; background:var(--fg-2); border-radius:6px; }
.meter em { position:absolute; top:0; bottom:0; width:2px; background:var(--warn); }
.spread { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }
.chip { padding:6px 10px; border-radius:8px; background:var(--panel-2); font-size:13px; }
.seg { border-radius:10px; border-color:var(--line); }
.seg button { font:500 13px var(--font-body); padding:10px 14px; min-height:44px; background:none; }
.seg button[disabled] { color:var(--fg-3); opacity:.6; cursor:not-allowed; }
.btn { border-radius:10px; font:500 13px var(--font-body); background:none; }
details > summary { cursor:pointer; color:var(--fg-2); font-size:13px; list-style:none; }
details > summary::before { content:"▸ "; color:var(--fg-3); }
details[open] > summary::before { content:"▾ "; }
details.block > summary { font-size:15px; color:var(--fg); }
.why-box { border-top:1px solid var(--line-2); margin-top:12px; padding-top:14px; }
tr.off { background:var(--discharge-soft); }
.alerts { display:flex; flex-direction:column; }
.alert { background:var(--discharge-soft); padding:10px 32px; font-size:14px; }
.alert b { color:var(--fault); margin-right:8px; }
.rec { border:1px solid var(--warn); border-radius:12px; padding:14px; display:flex; flex-direction:column; gap:10px; background:var(--panel); }
.hold { position:relative; overflow:hidden; touch-action:none; }
.hold.holding { box-shadow:inset 0 0 0 2px var(--fault); }
a { color:var(--charge); }
/* overview */
.card { background:var(--panel); border-radius:14px; padding:18px 22px; min-width:0; }
.card-head { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:12px; }
.card-head h2 { margin:0; }
.grid-2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr)); gap:20px; }
.grid-3 { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:20px; }
.span-3 { grid-column:1 / -1; }
.hours { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(64px,1fr); gap:6px; padding-bottom:6px; scroll-snap-type:x mandatory; }
.hour { display:flex; flex-direction:column; align-items:center; gap:4px; padding:10px 4px; border-radius:10px; background:var(--panel-2); scroll-snap-align:start; }
.hour .rain { color:var(--charge); }
.span-2 { grid-column:span 2; }
.hero .money { flex:1 1 260px; max-width:360px; }
.ic { flex:none; vertical-align:-4px; }
#flow > .scroll-x { overflow-y:hidden; }
.flowbox { position:relative; height:340px; }
.flowbox.vertical { height:500px; }
.flow-lines { position:absolute; inset:0; width:100%; height:100%; }
.fnode { position:absolute; transform:translate(-50%,-50%); box-sizing:border-box; display:flex; align-items:center; gap:10px; background:var(--panel-2); border:1px solid var(--line); border-radius:12px; padding:8px 12px; opacity:.6; white-space:nowrap; width:20%; min-width:0; overflow:hidden; }
.fnode > div { min-width:0; }
.fnode.on { opacity:1; border-color:var(--c); box-shadow:inset 3px 0 0 var(--c); }
.fnode span { display:block; font-size:12px; color:var(--fg-3); }
.fnode b { display:block; font-size:16px; }
.fnode i { display:block; font-style:normal; font-size:12px; color:var(--fg-3); overflow:hidden; text-overflow:ellipsis; }
.fhouse { position:absolute; left:50%; top:50%; width:20%; transform:translate(-50%,-50%); background:var(--panel-2); border:1px solid var(--use); border-radius:14px; padding:14px; text-align:center; }
.fhouse b { display:block; font-size:24px; margin-top:4px; }
.fhouse span { font-size:12px; color:var(--fg-3); }
/* upright on phones: small stacked tiles, icon above the text */
.flowbox.vertical .fnode { width:30%; flex-direction:column; gap:4px; padding:8px 6px; text-align:center; white-space:normal; }
.flowbox.vertical .fnode.on { box-shadow:inset 0 3px 0 var(--c); }
.flowbox.vertical .fnode b { font-size:15px; }
.flowbox.vertical .fnode i { white-space:nowrap; }
.flowbox.vertical .fhouse { width:44%; padding:10px; }
.flowbox.vertical .fhouse b { font-size:20px; }
.flowbox.vertical.many .fnode { width:23%; }
@media (prefers-reduced-motion: no-preference) { .flow { animation:flow 1.2s linear infinite; } .flow.rev { animation-direction:reverse; } @keyframes flow { to { stroke-dashoffset:-24; } } }
.next { font-size:19px; color:var(--fg); }
.spark { margin-bottom:10px; }
.spark-head { display:flex; align-items:baseline; gap:8px; }
.spark-head span { font-size:13px; color:var(--fg-2); }
.spark-head b { font-size:17px; margin-left:auto; }
.spark-head i { font-style:normal; font-size:12px; color:var(--fg-3); min-width:70px; text-align:right; }
.spark svg { display:block; width:100%; height:56px; }
.spark-axis { display:flex; justify-content:space-between; font-size:11px; }
.wx { display:flex; gap:16px; align-items:center; }
.wx > div { display:flex; flex-direction:column; gap:2px; min-width:0; }
.wx b.big { font-size:26px; font-weight:500; }
.sunbars { display:flex; align-items:flex-end; gap:4px; height:84px; }
.sunbars > div { flex:1 1 0; height:100%; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; gap:4px; }
.sunbars i { width:100%; background:var(--pv); border-radius:3px 3px 0 0; }
.sunbars span { font-size:10px; color:var(--fg-3); }
.devs { display:flex; flex-direction:column; }
.dev { display:grid; grid-template-columns:150px minmax(0,1fr) auto auto; gap:12px; align-items:center; padding:10px 0; border-top:1px solid var(--line-2); }
.dev-name { display:flex; align-items:center; gap:8px; }
.dev .seg button { min-height:36px; padding:6px 10px; }
.dev-ctl { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:0 0 10px 150px; }
/* decisions */
.chips { display:flex; flex-wrap:wrap; gap:8px; }
.chips .chip b { margin-left:6px; }
table.dec td { vertical-align:middle; }
.act { display:inline-block; padding:3px 9px; border-radius:6px; font-size:12px; background:var(--panel-2); color:var(--fg-2); white-space:nowrap; }
.act-charge { background:var(--charge); color:var(--bg); }
.act-discharge { background:var(--discharge); color:var(--bg); }
.vbars { display:flex; flex-direction:column; gap:3px; width:180px; margin-bottom:3px; }
.vb { display:block; height:5px; background:var(--panel-2); border-radius:3px; overflow:hidden; }
.vb > i { display:block; height:100%; border-radius:3px; }
/* wall tablet */
:host([kiosk]) main { padding:36px 44px; max-width:none; }
.kiosk { display:flex; flex-direction:column; gap:28px; }
.kiosk .spread { font-size:17px; }
h1.huge { font-size:58px; line-height:1.05; }
.why.big { font-size:21px; }
:host([kiosk]) .live dd { font-size:40px; }
:host([kiosk]) .live dt { font-size:16px; }
:host([kiosk]) .live .sub { font-size:14px; }
/* narrow screens: everything stacks */
@media (max-width: 860px) {
  header.top { padding:0 10px 0 4px; gap:10px; }
  header .title { display:none; }        /* the sidebar already says HEMS; the three tabs need the room */
  nav.tabs { gap:16px; }
  nav.tabs button { font-size:14px; }
  .pill { display:none; }
  main { padding:20px 14px 36px; gap:24px; }
  h1 { font-size:24px; }
  .two { grid-template-columns:1fr; gap:24px; }
  .grid-3 { grid-template-columns:1fr; }
  .span-2 { grid-column:auto; }
  .dev { grid-template-columns:1fr auto; }
  .dev-ctl { padding-left:0; }
  .device { grid-template-columns:1fr; padding:18px; }
  .device.thin { grid-template-columns:1fr; padding:4px 18px; }
  .live { gap:18px; }
  .live dd { font-size:20px; }
}
`;

/**
 * The old battery manager's action text as charge, discharge or idle. Its states start with the mode and carry a power:
 * 'Charging 5060W', 'Discharging 8000W', 'Adaptive 700W' and 'Adaptive Discharging 300W' (adaptive = discharging to
 * follow the house), 'Opportunistic Solar (1230W excess)' (charging on solar), 'Passive Solar (...)', 'Idle | Upcoming:
 * Charge ...' (the upcoming part must not count). A power of 0 W is idle.
 */
/* The old battery manager's status in HEMS terms, by what it asks of the grid. Its "Adaptive" (cover the house, follow the grid) and
   "Opportunistic/Passive Solar" (store surplus) are what HEMS calls idle: self-consumption. Only a forced charge, a scheduled discharge or
   an adaptive discharge at selling power counts as charge or discharge. */
function otherAction(v) {
  const x = String(v || "").trim().toLowerCase();
  if (!x || x === "unknown" || x === "unavailable") return null;
  const watts = x.replace(/\(.*?\)/g, "").match(/(\d+)\s*w\b/);       // a figure in brackets is a note, not the power
  const w = watts ? Number(watts[1]) : 0;
  if (x.startsWith("charging")) return w > 0 ? "charge" : "idle";
  if (x.startsWith("discharging")) return w > 0 ? "discharge" : "idle";
  if (x.startsWith("adaptive") && w >= OTHER_SELL_W) return "discharge";
  return "idle";
}

/* The SAJ slots HEMS would write (advisory): nothing is sent to the inverter until auto is opened in phase 4. */
function wouldWriteHtml(saj) {
  if (!saj) return "";
  const row = (s, kind) => `<tr><td class="c-${kind}">${kind === "charge" ? "Charge" : "Sell"}</td><td class="mono">${esc(s.start)}–${esc(s.end)}</td><td class="n">${s.power_pct} %</td><td class="n">${num(s.kwh, 1)} kWh</td></tr>`;
  const rows = [...saj.charge.map((s) => row(s, "charge")), ...saj.discharge.map((s) => row(s, "discharge"))].join("");
  const state = saj.missing.length ? `<span class="c-fault">${saj.missing.length} SAJ entities missing</span>`
    : saj.writes ? `${saj.writes} changes from what the inverter has now` : "the inverter already has this";
  return `<details><summary>Would write</summary><div class="stack" style="margin-top:12px">
    <p class="quiet small">SAJ time slots for the next 24 hours, rebuilt every quarter. Nothing is written yet. Mode would be ${saj.mode === 1 ? "Time-of-use" : "Self-consumption"}; ${state}.${saj.merge_cost_eur ? ` Merging short pauses costs € ${num(saj.merge_cost_eur, 2)}.` : ""}</p>
    ${rows ? `<div class="scroll-x"><table><tr><th>Slot</th><th>Time</th><th>Power</th><th>Energy</th></tr>${rows}</table></div>` : `<p class="quiet small">No slots: self-consumption all day.</p>`}
  </div></details>`;
}

function configureLink(s) {
  return s ? `<a data-nav href="/config/integrations/integration/hems" class="small">Change in HEMS settings →</a>` : "";
}

/** The battery's SoC limits as one bar: hard minimum, the sell floor band, the charge ceiling (draft values while editing). */
function socBarHtml(s, v) {
  const hard = Number(v("hard_min_soc_pct")), lo = Number(v("reserve_soc_pct")), hi = Number(v("reserve_max_soc_pct")), top = Number(v("max_soc_pct"));
  const pct = (x) => Math.max(0, Math.min(100, x));
  return `<div class="socbar" role="img" aria-label="Never below ${hard} %, sales stop between ${lo} and ${hi} %, charging up to ${top} %">
      <i class="floor" style="width:${pct(hard)}%"></i>
      <i class="band" style="left:${pct(lo)}%;width:${pct(Math.max(0, hi - lo))}%"></i>
      <i class="ceil" style="left:${pct(top)}%;width:${pct(100 - top)}%"></i>
    </div>
    <div class="spread quiet small"><span>never below ${num(hard, 0)} %</span><span>sales stop at ${num(lo, 0)}–${num(hi, 0)} %</span><span>charge up to ${num(top, 0)} %</span></div>`;
}

/** Learned values next to the configured ones; read-only, they stay set in Home Assistant. */
function learnedHtml(s) {
  const l = s.learned || {}, o = s.options;
  const rows = [];
  if (l.round_trip_eff) rows.push(`Round-trip efficiency: set ${num(o.round_trip_eff, 2)} · learned ${num(l.round_trip_eff.value, 2)}${l.round_trip_eff.source === "learned" ? ` (from ${num(l.round_trip_eff.charged_kwh, 1)} kWh charged)` : ` (${esc(l.round_trip_eff.source)})`}`);
  if (l.pv_gain_w_per_wm2) rows.push(`PV gain: set ${o.pv_gain_w_per_wm2 ? num(o.pv_gain_w_per_wm2, 2) : "automatic"} · in use ${num(l.pv_gain_w_per_wm2.value, 2)} W per W/m²`);
  return rows.length ? `<div class="learned">${rows.map((r) => `<p class="small">${r}</p>`).join("")}<p class="quiet small">Learned values are shown only; change the starting values in Home Assistant.</p></div>` : "";
}

function settingsInWords(o) {
  const yes = (v) => v ? "on" : "off";
  return [
    ["Battery", `${num(o.capacity_kwh, 0)} kWh usable, max ${num(o.max_power_kw, 1)} kW. Never below ${num(o.hard_min_soc_pct, 0)} %, sales stop at ${num(o.reserve_soc_pct, 0)}–${num(o.reserve_max_soc_pct ?? o.reserve_soc_pct, 0)} % (what the house needs until the next refill, × ${num(o.reserve_load_factor ?? 1, 2)}); below that the battery only covers the house. Efficiency ${num(o.round_trip_eff, 2)}; a cycle must earn € ${num(o.min_profit_margin, 2)} per kWh after losses. Holding cost € ${num(o.hold_cost_kwh_h, 3)} per kWh per hour.`],
    ["Water heater", o.water_heater_enabled ? `On. Day run ${num(o.water_heater_energy_kwh, 1)} kWh in ${o.water_heater_hours} h, legionella ${num(o.water_heater_legionella_energy_kwh, 1)} kWh on ${DAY_LABEL[o.water_heater_legionella_weekday] || esc(o.water_heater_legionella_weekday)}.` : "Off."],
    ["EV", o.ev_enabled ? `On (dry-run). ${num(o.ev_capacity_kwh, 1)} kWh battery, target ${num(o.ev_target_required_pct, 0)} % at the deadline, up to ${num(o.ev_target_max_pct, 0)} % below € ${num(o.ev_max_price, 2)}. ${num(o.ev_min_current_a, 0)}–${num(o.ev_max_current_a, 0)} A per phase; solar only for extra: ${yes(o.ev_solar_only)}.` : "Off."],
    ["Prices", `Nord Pool ${yes(o.nordpool_enabled)} (${esc(o.delivery_area)}). Import ×${num(o.import_vat_multiplier, 2)} + € ${num(o.import_markup, 4)} + energy tax € ${num(o.import_energy_tax, 5)}. Net metering ${yes(o.salderen)} until ${esc(o.salderen_until || "—")}.`],
    ["Solar and weather", `Weather ${yes(o.weather_enabled)}; PV peak ${num(o.pv_max_ac_w, 0)} W; gain ${o.pv_gain_w_per_wm2 ? num(o.pv_gain_w_per_wm2, 2) : "calibrated automatically"}.`],
    ["Grid connection", `${num(o.grid_limit_a, 0)} A per phase, ${num(o.grid_margin_a, 0)} A margin.`],
    ["Decision log", `Log the full plan every cycle: ${yes(o.trace_full_plan)}.`],
  ];
}

function windowsTable(p) {
  const ws = (p && p.windows) || [];
  if (!ws.length) return `<div class="empty">No charge or discharge windows planned.</div>`;
  return `<table><tr><th>Action</th><th>From</th><th>To</th><th>Active</th><th>kWh</th><th>kW</th><th>Avg. price</th><th>SoC</th></tr>
    ${ws.map((w) => `<tr><td class="c-${w.action}">${esc(ACTION_LABEL[w.action] || w.action)}</td><td class="mono">${dayShort(w.from)} ${hhmm(w.from)}</td><td class="mono">${hhmm(w.to)}</td><td class="n">${esc(duration(w.active_min))}</td>
      <td class="n">${num(w.kwh, 1)}</td><td class="n">${kw(Math.abs(w.power_w))}</td><td class="n">${eur(w.avg_price_eur_kwh)}</td><td class="n">${num(w.soc_from_pct, 0)} → ${num(w.soc_to_pct, 0)} %</td></tr>`).join("")}</table>`;
}

function sellTable(p) {
  const ws = (p && p.sell_windows) || [];
  if (!ws.length) return `<div class="empty">No sell windows in the horizon.</div>`;
  return `<table><tr><th>Window</th><th>Peak</th><th>Status</th><th>Sold</th><th>From stock</th></tr>
    ${ws.map((w) => `<tr><td class="mono">${dayShort(w.from)} ${hhmm(w.from)}–${hhmm(w.to)}</td><td class="n">${eur(w.peak)}</td>
      <td><span class="tag ${w.status === "unsold" ? "fault" : w.status === "planned" ? "ok" : "off"}">${esc(WINDOW_LABEL[w.status] || w.status)}</span></td>
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

/* Day rows summed into the chosen period: one bucket per day (last 30), ISO week (last 26), month (last 12) or year. */
function periodBuckets(days, period) {
  const keyOf = {
    day: (d) => d.date,
    week: (d) => isoWeek(d.date),
    month: (d) => d.date.slice(0, 7),
    year: (d) => d.date.slice(0, 4),
  }[period] || ((d) => d.date);
  const map = new Map();
  for (const d of days) {
    const k = keyOf(d);
    const b = map.get(k) || { key: k, gain: 0, cost: 0, baseline_cost: 0, stock_value: 0, import_kwh: 0, export_kwh: 0, pv_kwh: 0, load_kwh: 0, days: 0, today: false };
    for (const f of ["gain", "cost", "baseline_cost", "stock_value", "import_kwh", "export_kwh", "pv_kwh", "load_kwh"]) b[f] += Number(d[f] || 0);
    b.days += 1; b.today = b.today || !!d.today;
    map.set(k, b);
  }
  return [...map.values()].slice(-PERIOD_KEEP[period]);
}

/* ISO week label of a local date, e.g. "2026-W44". */
function isoWeek(iso) {
  const d = new Date(iso + "T12:00:00Z");
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day + 3);                          // the Thursday of this week decides the year
  const first = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  const week = 1 + Math.round(((d - first) / 864e5 - 3 + ((first.getUTCDay() + 6) % 7)) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

/* Bars of the gain per day, week, month or year; the running bucket is drawn lighter. */
function drawDays(host, svg, payload, period = "day") {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const rows = periodBuckets((payload.realised && payload.realised.daily) || [], period);
  const C = (v) => cssVar(host, v);
  const W = Math.max(320, svg.getBoundingClientRect().width || 600), H = 160, L = 46, top = 10, bot = H - 22;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("height", H);
  const el = (tag, a) => { const e = document.createElementNS(SVGNS, tag); for (const k in a) e.setAttribute(k, a[k]); svg.appendChild(e); return e; };
  const t = (txt, a) => { const e = el("text", { fill: C("--fg-3"), "font-size": 10, ...a }); e.textContent = txt; };
  if (!rows.length) { t("No full day measured yet", { x: W / 2, y: H / 2, "text-anchor": "middle" }); return; }
  const mx = Math.max(0.1, ...rows.map((d) => Math.abs(d.gain)));
  const zero = top + (bot - top) / 2, sy = (v) => zero - v / mx * (bot - top) / 2;
  el("line", { x1: L, x2: W - 4, y1: zero, y2: zero, stroke: C("--line") });
  t("+€ " + num(mx, 2), { x: L - 4, y: top + 8, "text-anchor": "end" }); t("−€ " + num(mx, 2), { x: L - 4, y: bot, "text-anchor": "end" });
  const bw = (W - L - 4) / rows.length;
  const label = (k) => period === "day" ? k.slice(5) : period === "week" ? k.slice(5) : period === "month" ? k.slice(2) : k;
  rows.forEach((d, i) => {
    const y = sy(d.gain);
    const r = el("rect", { x: L + i * bw + 1, y: Math.min(y, zero), width: Math.max(1, bw - 2), height: Math.abs(zero - y), fill: C(d.gain >= 0 ? "--ok" : "--fault"), "fill-opacity": d.today ? .5 : .85 });
    const tt = document.createElementNS(SVGNS, "title");
    tt.textContent = `${d.key}: ${num(d.gain, 2)} € (cost ${num(d.cost, 2)}, self-consumption ${num(d.baseline_cost, 2)}, stored ${num(d.stock_value, 2)}; ${d.days} day${d.days === 1 ? "" : "s"})`;
    r.appendChild(tt);
    if (rows.length <= 14 || i % 3 === 0) t(label(d.key), { x: L + i * bw + bw / 2, y: H - 6, "text-anchor": "middle" });
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
        <div class="pad" style="padding-bottom:0"><span class="eyebrow">${esc((this._config && this._config.title) || "HEMS · timeline")}</span></div>
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
  ["hems-timeline-card", "HEMS timeline", "Price, plan, SoC and forecasts on one time axis, with the reason per quarter."],
  ["hems-verdict-card", "HEMS now", "What HEMS would do now, why, and the decision chain."],
]) if (!window.customCards.some((c) => c.type === type)) window.customCards.push({ type, name, description, preview: false });
