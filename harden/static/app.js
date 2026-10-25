"use strict";
/* Harden Defense : l'interface ne montre que ce qu'un non-technicien comprend ; le détail est derrière un clic. */
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n || 0).toLocaleString("fr-FR");
const plural = (n, one, many) => (n > 1 ? many : one);
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- icônes (traits fins, héritent la couleur du texte) ---------- */
const ICONS = {
  "shield": '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z"/>',
  "shield-check": '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
  "shield-alert": '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z"/><path d="M12 8.5v4M12 16h.01"/>',
  "alert": '<path d="M12 3.5l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
  "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  "x": '<path d="M6 6l12 12M18 6L6 18"/>',
  "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  "eye": '<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.8"/>',
  "chevron": '<path d="M6 9l6 6 6-6"/>',
  "sparkle": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
  "door": '<rect x="5" y="3" width="14" height="18" rx="2"/><circle cx="15" cy="12" r="1"/>',
  "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3"/>',
  "pulse": '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  "board": '<rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="10" y="4" width="5" height="10" rx="1.5"/><rect x="17" y="4" width="4" height="13" rx="1.5"/>',
  "bell": '<path d="M6 16V11a6 6 0 0112 0v5l1.5 2h-15z"/><path d="M10 21h4"/>',
  "gear": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
  "send": '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
  "database": '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
};
const icon = (name) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;
document.querySelectorAll("[data-i]").forEach((el) => { el.innerHTML = icon(el.dataset.i); });
$("logo").innerHTML = icon("shield-check");

/* ---------- le vocabulaire : zéro jargon en première ligne ---------- */
const ATTACKS = {
  scan: { icon: "door", title: "Quelqu'un teste les portes", tech: "Scan de ports", what: "un test de portes" },
  ssh:  { icon: "key", title: "Quelqu'un devine un mot de passe", tech: "Bruteforce SSH", what: "une devinette de mot de passe" },
  icmp: { icon: "pulse", title: "Quelqu'un sature la machine", tech: "Flood ICMP", what: "une saturation de la machine" },
  sqli: { icon: "database", title: "Quelqu'un vise la base de données", tech: "Injection SQL", what: "une attaque sur la base de données" },
};
const COLUMNS = [
  { id: "waiting", icon: "clock", title: "Pas encore vue", sub: "En attente d'une attaque", empty: "Toutes les attaques ont déjà été observées." },
  { id: "passed", icon: "alert", title: "Repérée, mais passée", sub: "Détectée, rien ne l'a arrêtée", empty: "Aucune attaque n'est passée." },
  { id: "stopped", icon: "shield-check", title: "Arrêtée", sub: "Bloquée avant d'entrer", empty: "Rien n'a encore été arrêté." },
];
const ENGINE = { snort: "Snort", suricata: "Suricata" };

function ago(iso, now) {
  const s = Math.max(0, Math.round((new Date(now) - new Date(iso)) / 1000));
  if (s < 10) return "à l'instant";
  if (s < 60) return `il y a ${s} s`;
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return new Date(iso).toLocaleDateString("fr-FR");
}

/* ---------- 1. héros : la réponse à « suis-je en sécurité ? » ---------- */
function renderHero(d) {
  const states = d.attacks.map((a) => a.state);
  const stopped = states.filter((s) => s === "stopped").length;
  const passed = states.filter((s) => s === "passed").length;
  let tone, iconName, title, sub;
  if (stopped + passed === 0) {
    tone = "calm"; iconName = "shield";
    title = "Tout est calme";
    sub = "Aucune attaque détectée pour l'instant. Lance une attaque depuis Kali pour voir la défense réagir.";
  } else if (passed === 0) {
    tone = "safe"; iconName = "shield-check";
    title = "Tout est sous contrôle";
    sub = `${stopped} ${plural(stopped, "type d'attaque a été arrêté", "types d'attaques ont été arrêtés")} avant d'atteindre la machine.`;
  } else if (d.mode === "ips") {
    tone = "warn"; iconName = "shield-alert";
    title = "Presque tout est sous contrôle";
    sub = `${passed} ${plural(passed, "attaque a été repérée", "attaques ont été repérées")} mais pas arrêtée${passed > 1 ? "s" : ""}.`;
  } else {
    tone = "warn"; iconName = "shield-alert";
    title = `${plural(passed, "Une attaque est passée", "Des attaques sont passées")}`;
    sub = "Elles ont été repérées, mais en mode Surveillance rien ne les arrête. Passe en mode Protection pour les bloquer.";
  }
  $("hero").dataset.tone = tone;
  $("hero-icon").innerHTML = icon(iconName);
  $("hero-title").textContent = title;
  $("hero-sub").textContent = sub;

  $("seg-ids").innerHTML = `${icon("eye")}Surveillance`;
  $("seg-ips").innerHTML = `${icon("shield-check")}Protection`;
  $("seg-ids").classList.toggle("on", d.mode === "ids");
  $("seg-ips").classList.toggle("on", d.mode === "ips");
  $("mode-help").textContent = {
    ids: "On observe et on prévient, sans rien bloquer.",
    ips: "Les attaques repérées sont bloquées automatiquement.",
  }[d.mode] || "Le mode s'affichera dès que les sondes démarrent.";

  $("s-stopped").textContent = fmt(stopped);
  $("s-passed").textContent = fmt(passed);
  $("s-sources").textContent = fmt(d.totals.sources);
  $("s-stopped-sub").textContent = `sur ${d.attacks.length} types d'attaques`;
}

/* ---------- graphique : barres fines, une couleur par issue ---------- */
function barPath(x, y, w, h, r) {            // arrondi 4px en haut, base droite
  r = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}
let chartSig = "";
function renderChart(timeline) {
  const W = Math.max(280, Math.round($("chart").clientWidth) || 560);
  const sig = JSON.stringify(timeline) + W;
  if (sig === chartSig) return;
  chartSig = sig;
  const H = 124, padB = 22, padT = 6, n = timeline.length;
  const max = Math.max(3, ...timeline.map((t) => t.stopped + t.passed));
  const slot = W / n, bw = Math.min(14, slot - 6), plotH = H - padB - padT;
  const y = (v) => padT + plotH * (1 - v / max);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Attaques par minute sur les 30 dernières minutes">`;
  const empty = timeline.every((t) => !t.stopped && !t.passed);
  if (!empty) svg += `<line class="gl" x1="0" x2="${W}" y1="${y(max)}" y2="${y(max)}"/><text x="0" y="${y(max) - 4}">${max}</text>`;
  svg += `<line class="base" x1="0" x2="${W}" y1="${H - padB}" y2="${H - padB}"/>`;
  timeline.forEach((t, i) => {
    const x = i * slot + (slot - bw) / 2, base = H - padB;
    const hs = plotH * (t.stopped / max), hp = plotH * (t.passed / max), gap = t.stopped && t.passed ? 2 : 0;
    svg += `<g class="col" data-i="${i}">`;
    if (t.stopped) svg += `<path class="bar" d="${barPath(x, base - hs, bw, hs, t.passed ? 0 : 4)}" fill="var(--stopped)"/>`;
    if (t.passed) svg += `<path class="bar" d="${barPath(x, base - hs - gap - hp, bw, hp, 4)}" fill="var(--passed)"/>`;
    svg += `<rect class="hit" x="${i * slot}" y="0" width="${slot}" height="${H - padB}"/></g>`;
  });
  svg += `<text x="0" y="${H - 4}">il y a 30 min</text><text x="${W}" y="${H - 4}" text-anchor="end">maintenant</text>`;
  if (empty)
    svg += `<text class="none" x="${W / 2}" y="${H / 2 - 4}">Aucune activité pour l'instant</text>`;
  svg += "</svg>";
  const rows = timeline.filter((t) => t.stopped || t.passed).map((t) =>
    `<tr><td>${esc(t.minute.slice(11))}</td><td>${t.stopped}</td><td>${t.passed}</td></tr>`).join("");
  $("chart").innerHTML = svg + `<table class="sr"><caption>Attaques par minute</caption><thead><tr><th>Heure (UTC)</th><th>Arrêtées</th><th>Passées</th></tr></thead><tbody>${rows}</tbody></table>`;

  const tip = $("tip"), fig = $("chart").parentElement;
  $("chart").querySelectorAll(".col").forEach((g) => {
    g.addEventListener("mouseenter", () => {
      const t = timeline[+g.dataset.i];
      const local = new Date(t.minute + ":00Z").toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
      tip.innerHTML = `<b>${esc(local)}</b><br>${t.stopped} arrêtée${t.stopped > 1 ? "s" : ""} · ${t.passed} passée${t.passed > 1 ? "s" : ""}`;
      const r = g.getBoundingClientRect(), f = fig.getBoundingClientRect();
      tip.style.left = `${r.left - f.left + r.width / 2}px`;
      tip.style.top = `${r.top - f.top + 6}px`;
      tip.hidden = false;
    });
    g.addEventListener("mouseleave", () => { tip.hidden = true; });
  });
}

/* ---------- 2. kanban : les cartes changent de colonne (animation FLIP) ---------- */
const colEls = {}, cardEls = {};
const openCards = new Set();          // cartes dépliées par l'utilisateur
const colChoice = {};                 // colonnes ouvertes/fermées par l'utilisateur (accordéon mobile)
const narrow = matchMedia("(max-width: 960px)");
function buildBoard() {
  $("board").innerHTML = COLUMNS.map((c) => `
    <section class="col" data-col="${c.id}" aria-label="${esc(c.title)}">
      <button class="col-h" type="button" aria-expanded="true">
        <span class="col-ico">${icon(c.icon)}</span>
        <h3>${esc(c.title)}<small>${esc(c.sub)}</small></h3><span class="count">0</span><span class="chev">${icon("chevron")}</span></button>
      <div class="cards"></div><p class="empty">${esc(c.empty)}</p>
    </section>`).join("");
  COLUMNS.forEach((c) => {
    colEls[c.id] = document.querySelector(`.col[data-col="${c.id}"]`);
    colEls[c.id].querySelector(".col-h").addEventListener("click", () => {
      if (!narrow.matches) return;                      // sur grand écran, les 3 colonnes restent visibles
      colChoice[c.id] = colEls[c.id].classList.contains("closed");
      applyColumns();
    });
  });
}
let defaultCol = "passed";
function applyColumns() {
  COLUMNS.forEach((c) => {
    const open = !narrow.matches || (c.id in colChoice ? colChoice[c.id] : c.id === defaultCol);
    colEls[c.id].classList.toggle("closed", !open);
    colEls[c.id].style.order = narrow.matches && c.id === defaultCol ? -1 : "";
    colEls[c.id].querySelector(".col-h").setAttribute("aria-expanded", String(open));
  });
}
narrow.addEventListener("change", applyColumns);

function verdictCell(label, iconName, result) {
  const kind = !result ? "" : result.success ? "passed" : "stopped";
  const text = !result ? "pas testé" : result.success ? "passée" : "arrêtée";
  const ico = !result ? "clock" : result.success ? "alert" : "shield-check";
  return `<div class="cell ${kind}" title="${esc(result ? result.detail : "Pas encore testé dans ce mode")}">
    <small>${label}</small><b>${icon(ico)}${text}</b></div>`;
}
function cardHTML(a, now) {
  const m = ATTACKS[a.key], open = openCards.has(a.key);
  const when = a.last_ts ? ` · <span data-ts="${esc(a.last_ts)}">${esc(ago(a.last_ts, now))}</span>` : "";
  const hist = a.ids || a.ips
    ? `<div class="a-hist">${verdictCell("Surveillance", "eye", a.ids)}${verdictCell("Protection", "shield", a.ips)}</div>`
    : `<p class="muted">Pas encore testée.</p>`;
  return `<button class="a-head" type="button" aria-expanded="${open}"><span class="aico">${icon(m.icon)}</span>
      <span class="a-txt"><h4>${esc(m.title)}</h4><p>${esc(m.tech)}${when}</p></span><span class="chev">${icon("chevron")}</span></button>
    <div class="a-more" ${open ? "" : "hidden"}>${hist}</div>`;
}
function updateExpandAll() {
  const all = Object.keys(ATTACKS).every((k) => openCards.has(k));
  $("expand-all").textContent = all ? "Tout replier" : "Tout déplier";
}
$("board").addEventListener("click", (e) => {
  const head = e.target.closest(".a-head");
  if (!head) return;
  const key = head.closest(".acard").dataset.key;
  const open = !openCards.has(key);
  open ? openCards.add(key) : openCards.delete(key);
  head.setAttribute("aria-expanded", String(open));
  head.nextElementSibling.hidden = !open;
  updateExpandAll();
});
$("expand-all").addEventListener("click", () => {
  const all = Object.keys(ATTACKS).every((k) => openCards.has(k));
  Object.keys(ATTACKS).forEach((k) => (all ? openCards.delete(k) : openCards.add(k)));
  document.querySelectorAll(".acard").forEach((el) => {
    const open = openCards.has(el.dataset.key);
    el.querySelector(".a-head").setAttribute("aria-expanded", String(open));
    el.querySelector(".a-more").hidden = !open;
  });
  updateExpandAll();
});
function renderBoard(d, first) {
  if (!colEls.waiting) buildBoard();
  const before = {};
  Object.keys(cardEls).forEach((k) => { before[k] = cardEls[k].getBoundingClientRect(); });
  const counts = { waiting: 0, passed: 0, stopped: 0 };
  d.attacks.forEach((a) => {
    const el = cardEls[a.key] || (cardEls[a.key] = Object.assign(document.createElement("article"), { className: "acard" }));
    el.dataset.key = a.key;
    el.innerHTML = cardHTML(a, d.now);
    colEls[a.state].querySelector(".cards").appendChild(el);
    counts[a.state]++;
  });
  defaultCol = ["passed", "stopped", "waiting"].find((c) => counts[c] > 0) || "passed";
  COLUMNS.forEach((c) => {
    colEls[c.id].querySelector(".count").textContent = counts[c.id];
    colEls[c.id].querySelector(".empty").hidden = counts[c.id] > 0;
    colEls[c.id].classList.toggle("is-empty", counts[c.id] === 0);
  });
  applyColumns();
  updateExpandAll();
  if (first || reduceMotion || narrow.matches) return;
  Object.keys(cardEls).forEach((k) => {
    if (!before[k]) return;
    const after = cardEls[k].getBoundingClientRect();
    const dx = before[k].left - after.left, dy = before[k].top - after.top;
    if (Math.abs(dx) + Math.abs(dy) > 2)
      cardEls[k].animate([{ transform: `translate(${dx}px,${dy}px)`, zIndex: 2 }, { transform: "none", zIndex: 2 }],
        { duration: 650, easing: "cubic-bezier(.2,.8,.2,1)" });
  });
}

/* ---------- 3. alertes : une phrase simple, le détail au clic ---------- */
const openEvents = new Set();
let feedSig = "", showAll = false;
function renderFeed(d) {
  const sig = JSON.stringify(d.recent.map((a) => [a.id, a.hits, a.last_ts])) + showAll;
  $("ai-src").textContent = d.ai_source === "claude" ? "Expliquées par l'IA" : "";
  if (sig === feedSig) return;
  feedSig = sig;
  if (!d.recent.length) {
    $("feed").innerHTML = `<div class="empty">Aucune alerte pour l'instant.<br>Elles apparaîtront ici dès qu'une attaque sera repérée.</div>`;
    $("more").hidden = true;
    return;
  }
  const list = showAll ? d.recent : d.recent.slice(0, 6);
  $("feed").innerHTML = list.map((a) => {
    const blocked = a.action === "blocked", m = ATTACKS[a.key] || { what: "une activité suspecte" };
    const dst = a.dst_port ? `${a.dst_ip}:${a.dst_port}` : a.dst_ip;
    const ai = a.summary ? `
      <div class="ev-ai"><div class="ai-h">${icon("sparkle")}ANALYSE${a.source === "claude" ? " PAR L'IA" : ""}</div>
        <p>${esc(a.summary)}</p><p><b>Que faire ?</b> ${esc(a.advice)}</p></div>` : "";
    return `
    <details class="ev" data-id="${a.id}" data-a="${blocked ? "blocked" : "alert"}" ${openEvents.has(a.id) ? "open" : ""}>
      <summary><span class="ev-dot">${icon(blocked ? "shield-check" : "eye")}</span>
        <span class="ev-text"><b>${esc(ENGINE[a.engine])}</b> a ${blocked ? "arrêté" : "repéré"} ${esc(m.what)}
        <time data-ts="${esc(a.last_ts || a.ts)}">${esc(ago(a.last_ts || a.ts, d.now))}</time></span><span class="chev">${icon("chevron")}</span></summary>
      <div class="ev-body">${ai}
        <dl class="facts">
          <div><dt>Venant de</dt><dd>${esc(a.src_ip)}</dd></div><div><dt>Visant</dt><dd>${esc(dst)}</dd></div>
          <div><dt>Paquets</dt><dd>${fmt(a.hits)}</dd></div><div class="wide"><dt>Règle déclenchée</dt><dd>${esc(a.signature)}</dd></div>
        </dl></div>
    </details>`;
  }).join("");
  $("feed").querySelectorAll("details").forEach((el) => el.addEventListener("toggle", () => {
    el.open ? openEvents.add(+el.dataset.id) : openEvents.delete(+el.dataset.id);
  }));
  const extra = d.recent.length - 6;
  $("more").hidden = extra <= 0;
  $("more").textContent = showAll ? "Réduire la liste" : `Afficher ${extra} alerte${extra > 1 ? "s" : ""} de plus`;
}
$("more").addEventListener("click", () => { showAll = !showAll; feedSig = ""; tick(); });

/* ---------- colonne de droite ---------- */
function renderSources(list) {
  if (!list.length) { $("sources").innerHTML = `<div class="empty">Personne n'a attaqué pour l'instant.</div>`; return; }
  $("sources").innerHTML = list.map((s) => {
    const done = Math.min(s.stopped, s.attempts), pct = (done / s.attempts) * 100;
    return `<div class="src">
      <div class="src-h"><span class="avatar">${icon("monitor")}</span><code>${esc(s.src_ip)}</code>
        <span class="n">${fmt(s.attempts)} ${plural(s.attempts, "tentative", "tentatives")}</span></div>
      <div class="split" role="img" aria-label="${done} arrêtée(s) sur ${s.attempts}">
        ${done ? `<i class="s" style="width:${pct}%"></i>` : ""}${s.attempts > done ? `<i class="p" style="width:${100 - pct}%"></i>` : ""}</div>
      <small>${done} arrêtée${done > 1 ? "s" : ""} sur ${s.attempts}</small></div>`;
  }).join("");
}
function renderGuardians(e) {
  $("guardians").innerHTML = `
    <div class="g snort"><span class="g-ico">${icon("eye")}</span>
      <div><h3>Snort <span class="tag">IDS</span></h3><p>Le guetteur : voit tout, ne bloque rien</p></div>
      <div class="num"><b>${fmt(e.snort.incidents)}</b><span>repérées</span></div></div>
    <div class="g suri"><span class="g-ico">${icon("shield-check")}</span>
      <div><h3>Suricata <span class="tag">IPS</span></h3><p>Le videur : peut stopper les attaques</p></div>
      <div class="num"><b>${fmt(e.suricata.blocked)}</b><span>arrêtées</span></div></div>`;
}

/* ---------- navigation : une vue à la fois ---------- */
const TABS = ["attaques", "alertes", "sources", "gardiens", "reglages"];
let currentTab = TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "attaques";
let seenAlerts = null, alertTotal = 0;
function setTab(name, { scroll = false } = {}) {
  currentTab = name;
  TABS.forEach((t) => {
    const on = t === name;
    $("tab-" + t).setAttribute("aria-selected", String(on));
    $("tab-" + t).tabIndex = on ? 0 : -1;
    $("panel-" + t).hidden = !on;
  });
  if (name === "alertes") seenAlerts = alertTotal;
  if (name === "reglages" && typeof openSettings === "function") openSettings();
  try { history.replaceState(null, "", "#" + name); } catch (e) { /* sans importance */ }
  updateBadges();
  if (scroll) {
    const top = $("panels").getBoundingClientRect().top + scrollY - 16;
    if (scrollY > top) scrollTo({ top, behavior: reduceMotion ? "auto" : "smooth" });
  }
}
$("tabs").addEventListener("click", (e) => {
  const b = e.target.closest("[data-tab]");
  if (b) setTab(b.dataset.tab, { scroll: true });
});
$("tabs").addEventListener("keydown", (e) => {           // flèches gauche/droite entre les onglets
  const i = TABS.indexOf(currentTab);
  const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1 }[e.key];
  if (next === undefined) return;
  e.preventDefault();
  setTab(TABS[(next + TABS.length) % TABS.length]);
  $("tab-" + currentTab).focus();
});
function badge(id, text, cls) {
  const el = $(id);
  el.hidden = !text;
  el.textContent = text === true ? "" : text || "";
  el.className = "t-badge" + (cls ? " " + cls : "");
}
function updateBadges() {
  if (!lastData) return;
  const passed = lastData.attacks.filter((a) => a.state === "passed").length;
  badge("b-attaques", passed ? String(passed) : "", "warn");
  badge("b-sources", lastData.top_attackers.length ? String(lastData.top_attackers.length) : "");
  const fresh = seenAlerts !== null && alertTotal > seenAlerts && currentTab !== "alertes";
  badge("b-alertes", fresh ? true : "", "dot");
}

/* ---------- activité : repliée par défaut ---------- */
$("act-toggle").addEventListener("click", () => {
  const open = $("act-toggle").getAttribute("aria-expanded") !== "true";
  $("act-toggle").setAttribute("aria-expanded", String(open));
  $("act-panel").hidden = !open;
  $("act-label").textContent = open ? "Masquer l'activité" : "Voir l'activité";
  if (open && lastData) { chartSig = ""; renderChart(lastData.timeline); }
});

/* ---------- boucle ---------- */
let firstLoad = true;
function refreshTimes(now) {
  document.querySelectorAll("time[data-ts], .a-foot [data-ts]").forEach((el) => {
    if (el.dataset.ts) el.textContent = ago(el.dataset.ts, now);
  });
}
let lastData = null;
function render(d) {
  lastData = d;
  renderHero(d);
  if (!$("act-panel").hidden) renderChart(d.timeline);
  renderBoard(d, firstLoad);
  renderFeed(d);
  renderSources(d.top_attackers);
  renderGuardians(d.engines);
  alertTotal = d.engines.snort.incidents + d.engines.suricata.incidents;
  if (seenAlerts === null || currentTab === "alertes") seenAlerts = alertTotal;
  updateBadges();
  refreshTimes(d.now);
  $("live").className = "live on";
  $("updated").textContent = "En direct · " + new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  firstLoad = false;
}
async function tick() {
  try {
    const r = await fetch("/api/summary", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    render(await r.json());
  } catch (e) {
    $("live").className = "live";
    $("updated").textContent = "Connexion perdue…";
  }
}
addEventListener("resize", () => { if (lastData && !$("act-panel").hidden) renderChart(lastData.timeline); });
setTab(currentTab);
tick();
setInterval(tick, 3000);
