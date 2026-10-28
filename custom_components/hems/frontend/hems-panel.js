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
 * URL options: ?kiosk (one screen for the wall tablet), ?theme=dark|light (force a theme), #today|plan|devices|insights|settings (older hashes still land on the right view).
 */

const VERSION = "0.5.0";
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
  const e = p.execution, act = d.action || "idle";
  const w = e && e.code !== "no_plan" ? e.power_w : d.power_w;
  const lead = act === "charge" ? `Charging the battery at ${kw(Math.abs(w))} kW.` : act === "discharge" ? `Selling from the battery at ${kw(Math.abs(w))} kW.` : "Holding the battery.";
  const ch = nextWindow(p, "charge"), dis = nextWindow(p, "discharge");
  const parts = [];
  // the active time goes with the window: a sale between 16:30 and 19:30 with pauses is not three hours of selling
  if (ch && act !== "charge") parts.push({ word: "Charging", text: span(ch.from, ch.to), time: ch.active_min, cls: "c-charge" });
  if (dis && act !== "discharge") parts.push({ word: parts.length ? "selling" : "Selling", text: span(dis.from, dis.to), time: dis.active_min, cls: "c-discharge" });
  const paused = (w) => w && w.active_min && w.active_min < (new Date(w.to) - new Date(w.from)) / 60000 - 1;
  parts.forEach((x, i) => { x.paused = paused(i === 0 && ch && act !== "charge" ? ch : dis); });
  const rest = parts.map((x) => `${x.word} ${x.paused ? duration(x.time) + " between " : ""}<span class="${x.cls}">${esc(x.text)}</span>`).join(", ");
  const c = d.compare || {};
  const why = c.code === "hold" ? `Selling now pays ${eur(c.sell, 3)} €/kWh; keeping it for later is worth ${eur(c.keep, 3)}.`
    : c.code === "sell" ? `Selling now pays ${eur(c.sell, 3)} €/kWh, more than keeping it (${eur(c.keep, 3)}).`
    : c.code === "buy" ? `Buying now costs ${eur(c.buy, 3)} €/kWh, less than it is worth later (${eur(c.keep, 3)}).`
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

/* ------------------------------------------------------------------ the panel */

const VIEWS = [["today", "Today"], ["plan", "Plan"], ["devices", "Devices"], ["insights", "Insights"]];
// earlier releases had more views and Dutch names; old bookmarks and the wall tablet URL land on the view that now holds them
const VIEW_ALIAS = {
  nu: "today", now: "today", prijzen: "insights", prices: "insights", leren: "insights", learn: "insights",
  batterij: "devices", battery: "devices", auto: "devices", ev: "devices", boiler: "devices", "water-heater": "devices", net: "devices", grid: "devices",
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
    this._view = viewOf(location.hash) || "today";
    this._hours = 24;
    this._period = "day";                 // Insights: day, week, month or year
    this._sel = null;
    this._confirm = false;
    this._details = false;
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
  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }
  set route(v) { this._route = v; }

  connectedCallback() {
    for (const prop of ["narrow", "panel", "route", "hass"]) upgradeProperty(this, prop);
    this.toggleAttribute("kiosk", this._kiosk);
    this._off = store.on(() => this._render());
    window.addEventListener("hashchange", this._onHash);
    window.addEventListener("resize", this._onResize);
    this._tick = setInterval(() => this._liveUpdate(), 15000);
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

  _go(view) { if (location.hash !== "#" + view) history.replaceState(null, "", "#" + view); this._view = view; this._sel = null; this._render(); }

  _liveUpdate() {
    // live numbers and phase bars follow every state change; the rest only a new payload
    const root = this.shadowRoot;
    if (!root || !this._hass) return;
    const p = store.payload, s = store.settings;
    const live = root.getElementById("live"); if (live) live.innerHTML = liveNumbersHtml(this._hass, p, s);
    const ph = root.getElementById("phases"); if (ph) ph.innerHTML = phasesHtml(this._hass, s);
    const clock = root.getElementById("clock"); if (clock) clock.textContent = hhmm(Date.now());
  }

  _render() {
    if (!this._hass) return;
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
    this.shadowRoot.querySelectorAll("[data-period]").forEach((b) => b.addEventListener("click", () => { this._period = b.dataset.period; this._render(); }));
    this._bindActions();
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

  /* ---------------- Today */
  _view_today(p, s) {
    const h = headline(p);
    const d = p && p.decision;
    return `
      <section class="hero">
        <div class="say">
          <span class="quiet">Now · ${hhmm(Date.now())}</span>
          <h1>${esc(h.lead)} ${h.rest}</h1>
          <p class="why">${h.why}</p>
        </div>
        <div id="live">${liveNumbersHtml(this._hass, p, s)}</div>
      </section>
      ${recsHtml(p, this._applyId)}
      <section class="block chart">
        <div class="chart-head">
          <h2>Next ${this._hours} hours</h2>
          <span class="key"><i class="sw" style="background:var(--mid-bar)"></i>price</span>
          <span class="key"><i class="ln"></i>battery %</span>
          <span class="key"><i class="sw" style="background:var(--charge)"></i>charge</span>
          <span class="key"><i class="sw" style="background:var(--discharge)"></i>sell</span>
          <span class="sp"></span>${this._hoursSeg()}
        </div>
        <svg id="combined" style="display:block;width:100%"></svg>
      </section>
      <section class="two">
        <div>
          <h2>Coming up</h2>
          ${agendaHtml(p)}
          <p class="quiet small">${evLine(p)}</p>
        </div>
        <div>
          <h2>Today</h2>
          ${this._moneyRows(p, d)}
          <a href="#insights" data-view="insights" class="small">More in Insights →</a>
        </div>
      </section>`;
  }

  _moneyRows(p, d) {
    const r = p && p.realised, t = r && r.today;
    const signed = (v) => v === null || v === undefined ? "—" : (v > 0 ? "+ " : v < 0 ? "− " : "") + "€ " + num(Math.abs(v), 2);
    return `<div class="rows">
      <div><span>Expected gain</span><span class="mono">${d ? "€ " + num(d.expected_saving, 2) : "—"}</span></div>
      <div><span>Cost</span><span class="mono">${t && t.quarters ? "€ " + num(t.cost, 2) : "—"}</span></div>
      <div><span>Saved</span><span class="mono" style="color:var(${t && t.gain >= 0 ? "--ok" : "--fault"})">${t && t.quarters ? signed(t.gain) : "—"}</span></div>
    </div>`;
  }

  /* ---------------- Plan */
  _view_plan(p) {
    return `
      ${p && p.decision ? `<section class="say"><span class="quiet">Plan</span><h1 class="mid">${esc(p.decision.plan_text || "—")}</h1></section>` : ""}
      <section class="block">
        <div class="chart-head"><h2>Timeline</h2><span class="sp"></span>${this._hoursSeg()}</div>
        <svg id="tl" style="display:block;width:100%"></svg>
        <div class="why-box" id="why">${whyHtml(p, this._sel)}</div>
      </section>
      <section class="two">
        <div><h2>Windows</h2><div class="scroll-x">${windowsTable(p)}</div></div>
        <div><h2>Changes</h2>${diffHtml(p)}</div>
      </section>`;
  }

  /* ---------------- Devices */
  _view_devices(p, s) {
    const o = (s && s.options) || {};
    return `${this._batteryRow(p, s)}${o.ev_enabled ? this._evRow(p, s) : ""}${o.water_heater_enabled ? this._heaterRow(p, s) : ""}
      <section class="device thin">
        <div class="name"><h2>Grid connection</h2><span class="quiet small">${num(o.grid_limit_a, 0)} A per phase</span></div>
        <div id="phases">${phasesHtml(this._hass, s)}</div>
      </section>`;
  }

  _batteryRow(p, s) {
    const b = (p && p.battery) || {};
    const soc = stateNum(this._hass, s && s.roles && s.roles.soc_entity);
    const h = headline(p);
    return `<section class="device">
      <div class="name"><h2>Battery</h2><span class="quiet small">${num(b.capacity_kwh, 0)} kWh · max ${num(b.max_power_kw, 0)} kW</span></div>
      <div class="body">
        <p>${esc(h.lead)} ${h.rest}</p>
        <div class="meter"><i style="width:${soc ?? 0}%"></i><em style="left:${b.reserve_kwh / b.capacity_kwh * 100}%"></em></div>
        <div class="mono quiet small spread"><span>${soc === null ? "—" : num(soc, 0) + " % · " + num(soc / 100 * b.capacity_kwh, 1) + " kWh"}</span><span>reserve ${num(b.reserve_kwh / b.capacity_kwh * 100, 0)} % · floor ${num(b.floor_kwh / b.capacity_kwh * 100, 0)} %</span></div>
        <details><summary>Details</summary>
          <div class="stack" style="margin-top:12px">${verdictHtml(p, 24)}${chainHtml(p)}<div class="scroll-x">${sellTable(p)}</div></div>
        </details>
      </div>
      <div class="ctl"><span class="quiet small">Mode</span>${modeSegHtml(p, "battery")}</div>
    </section>`;
  }

  _evRow(p, s) {
    const ev = p && p.ev;
    const o = s.options;
    const days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"], short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const deadlines = days.map((d, i) => o["ev_deadline_" + d] ? `<span class="chip mono">${short[i]} ${esc(o["ev_deadline_" + d])}</span>` : "").join("");
    const evSoc = stateNum(this._hass, s.roles && s.roles.ev_soc_entity);
    const forceOn = this._hass.states["switch.hems_ev_force_charge"] && this._hass.states["switch.hems_ev_force_charge"].state === "on";
    const blocks = evBlocks(((p && p.quarters) || []).filter((r) => r.ev_a));
    const status = ev ? `${(EV_LABEL[ev.status] || ev.status).replace(/^./, (c) => c.toUpperCase())}.` : "No EV plan yet.";
    return `<section class="device ${ev && ev.status === "deadline_at_risk" ? "risk" : ""}">
      <div class="name"><h2>EV</h2><span class="quiet small">${num(o.ev_capacity_kwh, 1)} kWh · ${num(o.ev_min_current_a, 0)}–${num(o.ev_max_current_a, 0)} A</span></div>
      <div class="body">
        <p>${esc(status)}${evSoc === null ? "" : ` Car at ${num(evSoc, 0)} %.`}${ev && ev.shortfall_kwh > 0 ? ` <span class="c-fault">${num(ev.shortfall_kwh, 1)} kWh short.</span>` : ""}</p>
        <div class="row">${deadlines || `<span class="quiet small">No deadlines set.</span>`}<span class="quiet small">${num(o.ev_target_required_pct, 0)} % by a deadline · up to ${num(o.ev_target_max_pct, 0)} % below € ${num(o.ev_max_price, 2)}</span></div>
        ${blocks.length ? `<details><summary>${blocks.length} planned charging block${blocks.length > 1 ? "s" : ""}</summary><div class="scroll-x" style="margin-top:12px"><table><tr><th>Block</th><th>Current</th><th>Tier</th><th>Avg. price</th></tr>${blocks.map((b) => `<tr><td class="mono">${esc(span(b.from, b.to))}</td><td class="n">${num(b.a, 0)} A</td><td>${esc(TIER_LABEL[b.tier] || b.tier)}</td><td class="n">${eur(b.price)}</td></tr>`).join("")}</table></div></details>` : ""}
      </div>
      <div class="ctl"><span class="quiet small">Mode</span>${modeSegHtml(p, "ev")}
        ${this._confirm ? `<span class="small">${forceOn ? "Stop force charging?" : "Start force charging? Only the plan changes in dry-run."}</span>
          <div class="row"><button type="button" class="btn pri" data-act="force-yes">${forceOn ? "Stop" : "Start"}</button><button type="button" class="btn" data-act="force-no">Cancel</button></div>`
          : `<button type="button" class="btn" data-act="force">${forceOn ? "Force charging · stop…" : "Force charge…"}</button>`}
      </div>
    </section>`;
  }

  _heaterRow(p, s) {
    const o = s.options;
    const runs = (p && p.heating) || [];
    const wh = s.roles && s.roles.water_heater_entity && this._hass.states[s.roles.water_heater_entity];
    const temp = wh ? (wh.attributes.current_temperature ?? (Number.isFinite(Number(wh.state)) ? Number(wh.state) : null)) : null;
    const leg = p && p.alerts && p.alerts.legionella;
    const next = runs[0];
    return `<section class="device ${leg && leg.on ? "risk" : ""}">
      <div class="name"><h2>Water heater</h2><span class="quiet small">${num(o.water_heater_energy_kwh, 1)} kWh daily · legionella ${esc(DAY_LABEL[o.water_heater_legionella_weekday] || o.water_heater_legionella_weekday)}</span></div>
      <div class="body">
        <p>${temp === null ? "" : `Tank ${num(temp, 0)} °C. `}${next ? `${HEAT_LABEL[next.kind] === "heating" ? "Daily" : (HEAT_LABEL[next.kind] || next.kind).replace(/^./, (c) => c.toUpperCase())} run ${esc(span(next.from, next.to))}.` : "No run planned yet."}</p>
        <div class="row quiet small"><span>Last legionella run <b class="fg">${leg && leg.last ? esc(dayShort(leg.last)) : leg && leg.configured ? "unknown" : "no sensor assigned"}</b></span>${leg && leg.on ? `<span class="c-fault">overdue</span>` : ""}</div>
      </div>
      <div class="ctl"><span class="quiet small">Mode</span>${modeSegHtml(p, "water_heater")}</div>
    </section>`;
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
        <div class="spread"><h2>Settings</h2>${configureLink(s)}</div>
        ${settingsInWords(s.options).map(([h, t]) => `<div><b>${h}</b><p class="quiet small" style="margin:2px 0 0">${t}</p></div>`).join("")}
      </section>
      <details class="block"><summary>Entities</summary><div class="scroll-x" style="margin-top:12px"><table>
        ${Object.entries(s.roles).sort().map(([k, v]) => `<tr><td class="mono">${esc(k.replace(/_entity$|_entities$/, ""))}</td><td class="mono">${esc(Array.isArray(v) ? v.join(", ") : String(v))}</td><td class="mono small">${typeof v === "string" && v.includes(".") ? (this._hass.states[v] ? esc(this._hass.states[v].state) : `<span class="c-fault">missing</span>`) : ""}</td></tr>`).join("")}
      </table></div></details>
      <p class="quiet small mono">panel ${VERSION} · HEMS build ${esc((p && p.meta.build) || "?")}</p>`;
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
  header.top { padding:0 14px; gap:14px; }
  .pill { display:none; }
  main { padding:20px 14px 36px; gap:24px; }
  h1 { font-size:24px; }
  .two { grid-template-columns:1fr; gap:24px; }
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

function configureLink(s) {
  return s ? `<a data-nav href="/config/integrations/integration/hems" class="small">Change in HEMS settings →</a>` : "";
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
