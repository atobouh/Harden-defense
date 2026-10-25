"use strict";
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n || 0).toLocaleString("fr-FR");

const ICONS = {
  scan: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
  ssh: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  icmp: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  sqli: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
};

const seen = new Set();
let firstLoad = true;

function ago(iso, now) {
  const s = Math.max(0, Math.round((new Date(now) - new Date(iso)) / 1000));
  if (s < 5) return "à l'instant";
  if (s < 60) return `il y a ${s} s`;
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return new Date(iso).toLocaleDateString("fr-FR");
}

function setNumber(id, value) {
  const el = $(id), text = fmt(value);
  if (el.textContent !== text) el.textContent = text;
}

function renderMode(mode) {
  const el = $("mode");
  const map = {
    ips: ["pill pill-ips", "MODE IPS · prévention active"],
    ids: ["pill pill-ids", "MODE IDS · détection seule"],
    stopped: ["pill pill-muted", "Sondes arrêtées"],
  };
  const [cls, label] = map[mode] || ["pill pill-muted", "Mode inconnu"];
  el.className = cls;
  el.textContent = label;
}

function renderChart(timeline) {
  const W = 720, H = 210, padL = 28, padB = 24, padT = 8;
  const max = Math.max(4, ...timeline.map((t) => t.snort + t.suricata));
  const top = Math.ceil(max / 4) * 4;
  const bw = (W - padL) / timeline.length;
  const y = (v) => padT + (H - padT - padB) * (1 - v / top);
  let out = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Alertes par minute">`;
  for (let i = 0; i <= 4; i++) {
    const v = (top / 4) * i, yy = y(v);
    out += `<line class="grid" x1="${padL}" x2="${W}" y1="${yy}" y2="${yy}"/><text x="${padL - 6}" y="${yy + 3.5}" text-anchor="end">${v}</text>`;
  }
  timeline.forEach((t, i) => {
    const x = padL + i * bw + 2, w = Math.max(2, bw - 4);
    const hs = (H - padT - padB) * (t.snort / top), hu = (H - padT - padB) * (t.suricata / top);
    const base = H - padB;
    if (t.suricata) out += `<rect class="bar" x="${x}" y="${base - hu}" width="${w}" height="${hu}" rx="3" fill="var(--suri)"><title>${esc(t.minute.slice(11))} · Suricata : ${t.suricata}</title></rect>`;
    if (t.snort) out += `<rect class="bar" x="${x}" y="${base - hu - hs}" width="${w}" height="${hs}" rx="3" fill="var(--snort)"><title>${esc(t.minute.slice(11))} · Snort : ${t.snort}</title></rect>`;
    if (i % 5 === 0) out += `<text x="${x + w / 2}" y="${H - 6}" text-anchor="middle">${esc(new Date(t.minute + ":00Z").toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }))}</text>`;
  });
  if (timeline.every((t) => !t.snort && !t.suricata))
    out += `<text class="empty" x="${W / 2}" y="${H / 2}">Aucune alerte sur cette période — lance une attaque depuis Kali</text>`;
  $("chart").innerHTML = out + "</svg>";
}

function verdict(r) {
  if (!r) return '<span class="res res-none">non testé</span>';
  return r.success
    ? `<span class="res res-pass" title="${esc(r.detail)}"><i></i>Attaque passée</span>`
    : `<span class="res res-stop" title="${esc(r.detail)}"><i></i>Attaque bloquée</span>`;
}

function renderCompare(attacks) {
  $("cmp").innerHTML = attacks.map((a) => `
    <tr>
      <td><div class="atk"><span class="atk-ico"><svg viewBox="0 0 24 24">${ICONS[a.key]}</svg></span>${esc(a.name)}</div></td>
      <td class="num ${a.snort ? "" : "dim"}">${fmt(a.snort)}</td>
      <td class="num ${a.suricata ? "" : "dim"}">${fmt(a.suricata)}</td>
      <td class="num ${a.blocked ? "" : "dim"}" style="${a.blocked ? "color:var(--good)" : ""}">${fmt(a.blocked)}</td>
      <td>${verdict(a.ids)}</td><td>${verdict(a.ips)}</td>
    </tr>`).join("");
}

function renderFeed(recent, now) {
  if (!recent.length) {
    $("feed").innerHTML = '<div class="empty-state">En attente d\'attaques…<br>Depuis Kali : <code>./attack.sh IP_UBUNTU all</code></div>';
    return;
  }
  $("feed").innerHTML = recent.map((a) => {
    const blocked = a.action === "blocked";
    const fresh = !firstLoad && !seen.has(a.id);
    seen.add(a.id);
    const dots = Array.from({ length: 5 }, (_, i) => `<i class="${i < (a.level || 0) ? "on" : ""}"></i>`).join("");
    const ai = a.summary ? `
      <div class="ai"><div class="ai-h"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/></svg>
        Analyse ${a.source === "claude" ? "IA" : "automatique"}<span class="dots" title="Gravité ${a.level}/5">${dots}</span></div>
        <div>${esc(a.summary)}</div><div><em>Conseil :</em> ${esc(a.advice)}</div></div>` : "";
    return `
      <article class="alert ${blocked ? "blocked" : ""} ${fresh ? "fresh" : ""}">
        <div class="alert-h"><b>${esc(a.name)}</b>
          <span class="badge ${a.engine === "snort" ? "b-snort" : "b-suri"}">${a.engine === "snort" ? "Snort · IDS" : "Suricata · IPS"}</span>
          <span class="badge ${blocked ? "b-blocked" : "b-detected"}">${blocked ? "Bloquée" : "Détectée"}</span>
          <span class="when">${esc(ago(a.last_ts || a.ts, now))}</span></div>
        <div class="meta"><code>${esc(a.src_ip)}</code> → <code>${esc(a.dst_ip)}${a.dst_port ? ":" + esc(a.dst_port) : ""}</code> · ${esc(a.proto)} · ${fmt(a.hits)} paquet${a.hits > 1 ? "s" : ""}</div>
        ${ai}
      </article>`;
  }).join("");
}

function renderTop(list) {
  if (!list.length) { $("sources").innerHTML = '<div class="empty-state">Aucune source pour l\'instant.</div>'; return; }
  const max = Math.max(...list.map((s) => s.packets), 1);
  $("sources").innerHTML = list.map((s) => `
    <div class="src"><div class="src-h"><code>${esc(s.src_ip)}</code><span>${fmt(s.packets)} paquet${s.packets > 1 ? "s" : ""} · ${fmt(s.incidents)} incident${s.incidents > 1 ? "s" : ""}</span></div>
      <div class="meter"><i style="width:${Math.max(4, (s.packets / max) * 100)}%"></i></div></div>`).join("");
}

function render(d) {
  renderMode(d.mode);
  const t = d.totals;
  setNumber("k-inc", t.incidents); setNumber("k-blk", t.blocked); setNumber("k-det", t.detected); setNumber("k-att", t.attackers);
  $("k-inc-sub").textContent = `${fmt(t.packets)} paquets analysés`;
  setNumber("e-snort-n", d.engines.snort.incidents); setNumber("e-snort-b", d.engines.snort.blocked);
  setNumber("e-suri-n", d.engines.suricata.incidents); setNumber("e-suri-b", d.engines.suricata.blocked);
  renderChart(d.timeline);
  renderCompare(d.attacks);
  renderFeed(d.recent, d.now);
  renderTop(d.top_attackers);
  $("ai-src").textContent = d.ai_source === "claude" ? "Analysées par l'IA (Claude)" : "Explications intégrées";
  $("live").className = "live on";
  $("updated").textContent = "en direct · " + new Date().toLocaleTimeString("fr-FR");
  firstLoad = false;
}

async function tick() {
  try {
    const r = await fetch("/api/summary", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    render(await r.json());
  } catch (e) {
    $("live").className = "live";
    $("updated").textContent = "connexion perdue…";
  }
}
tick();
setInterval(tick, 3000);
