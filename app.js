"use strict";
// Halal Penny Screener: reads results/latest.csv + results/meta.json from this repo (GitHub Pages).

const PAGE = 60;
const DEFAULT_LIMITS = { debt_ratio: 0.30, cash_ratio: 0.30, income_ratio: 0.05 };
const state = { rows: [], meta: null, verdict: "PASS", q: "", sort: "market_cap", maxPrice: 5, minVol: 0, exch: "", shown: PAGE };
const $ = (id) => document.getElementById(id);

// ---------- storage (optional conveniences only) ----------
function load(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } }
function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ } }

// ---------- CSV ----------
function parseCSV(text) {
  const rows = []; let row = [], field = "", i = 0, inQ = false;
  while (i < text.length) {
    const c = text[i];
    if (inQ) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i += 2; continue; } inQ = false; i++; continue; }
      field += c; i++; continue;
    }
    if (c === '"') { inQ = true; i++; continue; }
    if (c === ",") { row.push(field); field = ""; i++; continue; }
    if (c === "\r") { i++; continue; }
    if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; continue; }
    field += c; i++;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const head = rows.shift() || [];
  return rows.filter((r) => r.length === head.length).map((r) => Object.fromEntries(head.map((h, j) => [h, r[j]])));
}

const NUM = ["price", "avg_volume_20d", "market_cap", "debt", "debt_ratio", "cash", "cash_ratio", "revenue", "interest_income", "income_ratio"];
function normalize(r) {
  for (const k of NUM) r[k] = r[k] === "" || r[k] == null ? null : Number(r[k]);
  r._search = (r.symbol + " " + r.name).toLowerCase();
  return r;
}

// ---------- formatting ----------
const money = (v) => {
  if (v == null || !isFinite(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1e9) return "$" + (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return "$" + (v / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return "$" + (v / 1e3).toFixed(0) + "K";
  return "$" + v.toFixed(0);
};
const price = (v) => (v == null ? "–" : "$" + (v < 1 ? v.toFixed(4).replace(/0{1,2}$/, "") : v.toFixed(2)));
const pct = (v, d = 0) => (v == null ? "–" : (v * 100).toFixed(v < 0.1 && v > 0 && d === 0 ? 1 : d) + "%");
const vol = (v) => (v == null ? "–" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : String(v));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const limits = () => ({ ...DEFAULT_LIMITS, ...((state.meta && state.meta.limits) || {}) });

// ---------- filtering ----------
function filtered(ignoreVerdict = false) {
  const q = state.q.trim().toLowerCase();
  return state.rows.filter((r) =>
    (ignoreVerdict || state.verdict === "ALL" || r.verdict === state.verdict) &&
    (!q || r._search.includes(q)) &&
    (r.price == null || r.price < state.maxPrice) &&
    (!state.minVol || (r.avg_volume_20d || 0) >= state.minVol) &&
    (!state.exch || r.exchange === state.exch));
}

function sorted(list) {
  const s = state.sort, out = list.slice();
  const desc = (k) => (a, b) => (b[k] ?? -Infinity) - (a[k] ?? -Infinity);
  if (s === "symbol") out.sort((a, b) => a.symbol.localeCompare(b.symbol));
  else if (s === "price_asc") out.sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
  else if (s === "debt_ratio") out.sort((a, b) => (a.debt_ratio ?? Infinity) - (b.debt_ratio ?? Infinity));
  else out.sort(desc(s));
  return out;
}

// ---------- rendering ----------
function ratioHTML(label, value, limit) {
  const over = value != null && value >= limit;
  const w = value == null ? 0 : Math.min(value / (limit * 2), 1) * 100;
  return `<div class="ratio">
    <div class="lbl"><span>${label}</span><span class="val${over ? " over" : ""}">${pct(value)}</span></div>
    <div class="track" title="limit ${pct(limit)}"><div class="fill${over ? " over" : ""}" style="width:${w}%"></div><div class="tick"></div></div>
  </div>`;
}

function cardHTML(r, i) {
  const L = limits();
  return `<li><button class="card" type="button" data-i="${i}">
    <div class="row1"><span class="sym">${esc(r.symbol)}</span><span class="badge ${esc(r.verdict)}">${esc(r.verdict)}</span><span class="price">${price(r.price)}</span></div>
    <div class="name">${esc(r.name)}</div>
    <div class="ratios">${ratioHTML("Debt", r.debt_ratio, L.debt_ratio)}${ratioHTML("Cash", r.cash_ratio, L.cash_ratio)}${ratioHTML("Interest", r.income_ratio, L.income_ratio)}</div>
    <div class="meta"><span>Mkt cap ${money(r.market_cap)}</span><span>Vol ${vol(r.avg_volume_20d)}</span><span>${esc(r.exchange)}</span></div>
    ${r.verdict !== "PASS" && r.reasons ? `<div class="reason">${esc(r.reasons)}</div>` : ""}
  </button></li>`;
}

let current = [];
function render() {
  const base = filtered(true);
  for (const chip of document.querySelectorAll(".chip")) {
    const v = chip.dataset.v;
    chip.setAttribute("aria-pressed", String(v === state.verdict));
    chip.querySelector(".n").textContent = v === "ALL" ? base.length : base.filter((r) => r.verdict === v).length;
  }
  current = sorted(filtered());
  const slice = current.slice(0, state.shown);
  $("list").innerHTML = slice.map((r, i) => cardHTML(r, i)).join("");
  $("count").textContent = `${current.length} stock${current.length === 1 ? "" : "s"}`;
  const L = limits();
  $("limits").textContent = `Limits: debt ${pct(L.debt_ratio)} · cash ${pct(L.cash_ratio)} · interest ${pct(L.income_ratio)}`;
  $("more").hidden = current.length <= state.shown;
  $("empty").hidden = current.length > 0 || !state.rows.length;
}

function openDetail(r) {
  const L = limits();
  const reasons = (r.reasons || "").split("; ").filter(Boolean);
  const verdictText = { PASS: "Passed every check", REVIEW: "Needs a manual check", FAIL: "Did not pass" }[r.verdict] || r.verdict;
  const cik = r.cik ? String(r.cik).padStart(10, "0") : "";
  const rowKV = (k, v) => `<tr><th>${k}</th><td>${v}</td></tr>`;
  const ratioRow = (k, v, lim) => rowKV(k, `<span class="${v != null && v >= lim ? "val over" : ""}">${pct(v, 1)}</span> <small style="color:var(--muted)">/ ${pct(lim)}</small>`);
  const cur = r.currency && r.currency !== "USD" ? ` (${esc(r.currency)})` : "";
  $("sheetbody").innerHTML = `
    <div class="head"><h2 id="d-sym">${esc(r.symbol)}</h2><span class="badge ${esc(r.verdict)}">${esc(r.verdict)}</span>
      <button class="iconbtn close" type="button" id="closebtn" aria-label="Close">✕</button></div>
    <div class="sname">${esc(r.name)} · ${esc(r.exchange)}</div>
    <div class="verdict ${esc(r.verdict)}"><b>${verdictText}</b>
      ${reasons.length ? `<ul>${reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "Business activity and all three ratios are within the limits."}</div>
    <div class="sec-title">Ratios</div>
    <table class="kv">
      ${ratioRow("Debt / market cap", r.debt_ratio, L.debt_ratio)}
      ${ratioRow("Cash + securities / market cap", r.cash_ratio, L.cash_ratio)}
      ${ratioRow("Interest / total income", r.income_ratio, L.income_ratio)}
    </table>
    <div class="sec-title">Numbers</div>
    <table class="kv">
      ${rowKV("Last price", price(r.price))}
      ${rowKV("Market cap", money(r.market_cap))}
      ${rowKV("Avg daily volume (20d)", vol(r.avg_volume_20d))}
      ${rowKV("Debt" + cur, money(r.debt))}
      ${rowKV("Cash + securities" + cur, money(r.cash))}
      ${rowKV("Revenue (12 mo)" + cur, money(r.revenue))}
      ${rowKV("Interest income (12 mo)" + cur, money(r.interest_income))}
      ${rowKV("Industry", esc(r.sic_description || "–") + (r.sic ? ` <small style="color:var(--muted)">SIC ${esc(r.sic)}</small>` : ""))}
      ${rowKV("Balance sheet date", esc(r.balance_sheet_date || "–"))}
      ${rowKV("Income period end", esc(r.income_period_end || "–"))}
    </table>
    <div class="links">
      ${cik ? `<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${cik}&type=10-&dateb=&owner=include&count=40" target="_blank" rel="noopener">SEC filings</a>` : ""}
      <a href="https://finance.yahoo.com/quote/${encodeURIComponent(r.symbol.replace(".", "-"))}" target="_blank" rel="noopener">Price chart</a>
    </div>
    <p class="note">Ratios use the latest filing on SEC EDGAR and the last close. Always read the company's own filings before deciding.</p>`;
  $("closebtn").onclick = () => $("sheet").close();
  $("sheet").showModal();
}

// ---------- data ----------
async function fetchFresh(url) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res;
}

async function loadData() {
  try {
    const [csvRes, metaRes] = await Promise.all([fetchFresh("results/latest.csv"), fetchFresh("results/meta.json").catch(() => null)]);
    state.rows = parseCSV(await csvRes.text()).map(normalize);
    state.meta = metaRes ? await metaRes.json() : null;
  } catch (e) {
    $("banner").innerHTML = `<div class="banner">Couldn't load results (${esc(e.message)}). Check your connection and reload.</div>`;
    $("runinfo").textContent = "No data";
    return;
  }
  const m = state.meta;
  const runDate = m ? new Date(m.run_date + "T12:00:00") : null;
  $("runinfo").textContent = m
    ? `Updated ${runDate.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} · ${m.screened.toLocaleString()} stocks under $${m.max_price}`
    : `${state.rows.length.toLocaleString()} stocks`;
  if (runDate && (Date.now() - runDate) / 864e5 > 14) {
    $("banner").innerHTML = `<div class="banner">These results are more than two weeks old. Prices and filings may have changed.</div>`;
  }
  const exchanges = [...new Set(state.rows.map((r) => r.exchange).filter(Boolean))].sort();
  $("exch").innerHTML = `<option value="">All</option>` + exchanges.map((x) => `<option>${esc(x)}</option>`).join("");
  $("exch").value = state.exch;
  render();
}

// ---------- events ----------
function bind() {
  const prefs = load("prefs", {});
  Object.assign(state, { verdict: prefs.verdict || "PASS", sort: prefs.sort || "market_cap", maxPrice: prefs.maxPrice || 5, minVol: prefs.minVol || 0, exch: prefs.exch || "" });
  $("sort").value = state.sort; $("maxprice").value = String(state.maxPrice); $("minvol").value = String(state.minVol);
  const persist = () => save("prefs", { verdict: state.verdict, sort: state.sort, maxPrice: state.maxPrice, minVol: state.minVol, exch: state.exch });
  const changed = () => { state.shown = PAGE; persist(); render(); window.scrollTo({ top: 0 }); };

  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => { state.verdict = c.dataset.v; changed(); }));
  let t; $("q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { state.q = e.target.value; state.shown = PAGE; render(); }, 120); });
  $("sort").addEventListener("change", (e) => { state.sort = e.target.value; changed(); });
  $("maxprice").addEventListener("change", (e) => { state.maxPrice = Number(e.target.value); changed(); });
  $("minvol").addEventListener("change", (e) => { state.minVol = Number(e.target.value); changed(); });
  $("exch").addEventListener("change", (e) => { state.exch = e.target.value; changed(); });
  $("filterbtn").addEventListener("click", () => {
    const open = $("filters").classList.toggle("open");
    $("filterbtn").setAttribute("aria-expanded", String(open));
  });
  $("more").addEventListener("click", () => { state.shown += PAGE; render(); });
  $("list").addEventListener("click", (e) => { const b = e.target.closest(".card"); if (b) openDetail(current[Number(b.dataset.i)]); });
  $("sheet").addEventListener("click", (e) => { if (e.target === $("sheet")) $("sheet").close(); });

  const applyTheme = (t) => { if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; };
  applyTheme(load("theme", ""));
  $("themebtn").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark"; applyTheme(next); save("theme", next);
  });
}

bind();
loadData();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
