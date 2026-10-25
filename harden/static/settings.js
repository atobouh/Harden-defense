"use strict";
/* Page « Réglages » : Telegram en 3 étapes, clé de l'IA en un bloc. Les secrets ne reviennent jamais du serveur. */
const settingsEl = $("settings");
let S = null;                               // dernier état reçu
const flash = {};                           // messages affichés sous chaque bloc
const pin = () => { try { return sessionStorage.getItem("hd-pin") || ""; } catch (e) { return ""; } };
let aiChoice = null;                        // fournisseur sélectionné dans le sélecteur

async function api(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (pin()) headers["X-Admin-Pin"] = pin();
  try {
    const r = await fetch(path, { method: body ? "POST" : "GET", headers, body: body ? JSON.stringify(body) : undefined, cache: "no-store" });
    const data = await r.json().catch(() => ({}));
    if (r.status === 403 || r.status === 429) return { ok: false, message: data.message || "Accès refusé.", denied: true };
    return data;
  } catch (e) {
    return { ok: false, message: "Le serveur ne répond pas. Vérifie que l'application tourne." };
  }
}
const msg = (key) => flash[key] ? `<p class="msg ${flash[key].ok ? "ok" : "err"}" role="status">${icon(flash[key].ok ? "check" : "alert")}<span>${esc(flash[key].text)}</span></p>` : "";

async function openSettings() { S = await api("/api/settings"); renderSettings(); }

/* ---------- code de sécurité (seulement pour un appareil distant) ---------- */
function pinCard() {
  if (!S.needs_pin || S.can_edit) return "";
  return `<section class="card set-card"><h3>Code de sécurité</h3>
    <p class="help">Pour modifier les réglages depuis cet appareil, entre le code affiché dans le terminal où tourne l'application (6 chiffres).
    Depuis l'ordinateur qui fait tourner l'application, aucun code n'est demandé.</p>
    <div class="row"><input class="input" id="pin-in" inputmode="numeric" maxlength="6" placeholder="123456" autocomplete="off" aria-label="Code de sécurité">
    <button class="btn" id="pin-go" type="button">Valider</button></div>${msg("pin")}</section>`;
}

/* ---------- Telegram ---------- */
function stepClass(done, locked) { return done ? "done" : locked ? "locked" : "current"; }
function telegramCard() {
  const t = S.telegram, ro = !S.can_edit ? "disabled" : "";
  const s1 = stepClass(t.token_set && !flash.tgChange, false), s2 = stepClass(t.chat_set, !t.token_set), s3 = stepClass(false, !t.chat_set);
  const choose = flash.chats ? `<div class="choices">${flash.chats.map((c) => `<button class="btn ghost" data-chat="${esc(c.id)}" type="button">${esc(c.name)}</button>`).join("")}</div>` : "";
  return `<section class="card set-card" aria-labelledby="tg-h">
    <div class="set-head"><span class="set-ico tg">${icon("send")}</span><div><h3 id="tg-h">Alertes Telegram</h3>
      <p class="help">Reçois chaque alerte sur ton téléphone, avec l'explication.</p></div>
      <span class="state ${t.chat_set ? "on" : ""}">${t.chat_set ? "Relié" : "Non relié"}</span></div>
    <ol class="steps">
      <li class="step ${s1}"><span class="num">${s1 === "done" ? icon("check") : "1"}</span><div class="step-body">
        <h4>Créer ton bot</h4>
        ${t.token_set && !flash.tgChange
          ? `<p class="help">Connecté au bot <b>@${esc(t.bot)}</b> · token ${esc(t.token_hint)} <button class="link" id="tg-change" type="button">Changer</button></p>`
          : `<p class="help">Dans Telegram, ouvre <b>@BotFather</b>, envoie <code>/newbot</code> et réponds aux deux questions. Il te donne un <b>token</b> (une longue suite de caractères) : colle-le ici.</p>
             <div class="row"><input class="input" id="tg-token" type="password" placeholder="123456789:AAH…" autocomplete="off" spellcheck="false" aria-label="Token du bot Telegram" ${ro}>
             <button class="btn" id="tg-token-go" type="button" ${ro}>Connecter</button></div>`}
        ${msg("tg1")}</div></li>
      <li class="step ${s2}"><span class="num">${s2 === "done" ? icon("check") : "2"}</span><div class="step-body">
        <h4>Relier ton compte</h4>
        ${t.chat_set
          ? `<p class="help">Compte relié : <b>${esc(t.chat_name || "ton compte")}</b>.</p>`
          : `<p class="help">Ouvre ton bot ${t.bot ? `(<a href="https://t.me/${esc(t.bot)}" target="_blank" rel="noopener">@${esc(t.bot)}</a>)` : ""} dans Telegram et envoie-lui <code>/start</code>. Puis clique :</p>
             <button class="btn" id="tg-chat-go" type="button" ${s2 === "locked" || ro ? "disabled" : ""}>Trouver mon compte</button>${choose}`}
        ${msg("tg2")}</div></li>
      <li class="step ${s3}"><span class="num">3</span><div class="step-body">
        <h4>Vérifier</h4>
        <p class="help">Un message de test part sur ton téléphone.</p>
        <button class="btn" id="tg-test-go" type="button" ${s3 === "locked" || ro ? "disabled" : ""}>Envoyer un message de test</button>
        ${msg("tg3")}</div></li>
    </ol>
    ${t.token_set ? `<button class="link danger" id="tg-clear" type="button" ${ro}>Déconnecter Telegram</button>` : ""}
  </section>`;
}

/* ---------- IA ---------- */
function aiStatus() {
  const a = S.ai, st = a.status;
  if (!a.key_set) return "";
  let line = "";
  if (st && st.ok) line = `<span class="dot ok"></span>Dernier lot : ${st.count} explication${st.count > 1 ? "s" : ""} · ${esc(st.model)} · ${esc(ago(st.at, new Date().toISOString()))}`;
  else if (st && !st.ok) line = `<span class="dot warn"></span>${esc(st.error)}`;
  else line = a.pending
    ? `<span class="dot"></span>Prête : ${a.pending} explication${a.pending > 1 ? "s seront demandées" : " sera demandée"} au prochain lot (moins de 10 secondes).`
    : `<span class="dot"></span>Prête : les nouvelles attaques seront expliquées automatiquement.`;
  const q = st && a.pending ? ` <span class="muted">· ${a.pending} en attente</span>` : "";
  return `<p class="ai-status">${line}${q}</p>`;
}
function aiCard() {
  const a = S.ai, ro = !S.can_edit ? "disabled" : "";
  if (!aiChoice) aiChoice = a.provider !== "none" ? a.provider : (a.choice === "none" ? "none" : "gemini");
  const has = aiChoice === "gemini" ? a.has_gemini_key : aiChoice === "claude" ? a.has_claude_key : false;
  const models = a.models[aiChoice] || [];
  const link = aiChoice === "gemini" ? `<a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">Obtenir une clé gratuite (Google AI Studio)</a>`
    : `<a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">Obtenir une clé (Anthropic)</a>`;
  const opts = (v, label) => `<button type="button" role="radio" aria-checked="${aiChoice === v}" data-ai="${v}" ${aiChoice === v ? 'class="on"' : ""}>${label}</button>`;
  const body = aiChoice === "none"
    ? `<p class="help">Sans IA, l'application utilise les explications écrites à l'avance. Tout fonctionne, avec des textes moins détaillés pour les attaques inconnues.</p>
       <button class="btn" id="ai-save" type="button" ${ro}>Enregistrer</button>`
    : `<p class="help">${has ? `Clé enregistrée ${aiChoice === a.provider ? esc(a.key_hint) : ""} ✓. Colle une nouvelle clé pour la remplacer.` : `Colle ta clé ici. ${link}`}</p>
       <div class="row"><input class="input" id="ai-key" type="password" placeholder="${has ? "Nouvelle clé (facultatif)" : "AIza… ou sk-ant-…"}" autocomplete="off" spellcheck="false" aria-label="Clé API" ${ro}>
       <button class="btn ghost" id="ai-eye" type="button" aria-label="Afficher ou masquer la clé">Afficher</button></div>
       <details class="adv"><summary>Options avancées</summary>
         <label class="help" for="ai-model">Modèle</label>
         <select class="input" id="ai-model" ${ro}>${models.map((m, i) => `<option value="${esc(m)}" ${m === a.model ? "selected" : ""}>${esc(m)}${i === 0 ? " (recommandé)" : ""}</option>`).join("")}</select></details>
       <div class="row end"><button class="btn" id="ai-save" type="button" ${ro}>Tester et enregistrer</button>
       ${has ? `<button class="link danger" id="ai-clear" type="button" ${ro}>Supprimer la clé</button>` : ""}</div>`;
  return `<section class="card set-card" aria-labelledby="ai-h">
    <div class="set-head"><span class="set-ico ai">${icon("sparkle")}</span><div><h3 id="ai-h">Explications par l'IA</h3>
      <p class="help">Chaque type d'attaque est expliqué en français simple, avec un conseil.</p></div>
      <span class="state ${a.key_set ? "on" : ""}">${a.key_set ? "Active" : "Intégrée"}</span></div>
    <div class="radio" role="radiogroup" aria-label="Fournisseur">${opts("gemini", "Gemini <small>gratuit</small>")}${opts("claude", "Claude")}${opts("none", "Aucune")}</div>
    ${body}${msg("ai")}${aiStatus()}
    <ul class="notes">
      <li>Les explications sont demandées <b>par lots</b> (jusqu'à ${a.batch_size} à la fois, ${a.max_rpm} requêtes par minute au maximum) pour rester sous la limite gratuite.</li>
      <li>Seuls le nom de la règle, la catégorie, le protocole et le port sont envoyés. <b>Jamais d'adresse IP.</b></li>
      <li>Si l'IA ne répond pas, l'application continue avec le texte intégré.</li></ul>
  </section>`;
}

/* ---------- rendu + actions ---------- */
function renderSettings() {
  if (!S) return;
  settingsEl.innerHTML = pinCard() + telegramCard() + aiCard() +
    `<p class="muted center">Les clés sont enregistrées dans <code>data/settings.json</code> sur cet ordinateur. Elles ne sont jamais affichées ni envoyées ailleurs qu'à Telegram et à l'IA choisie.</p>`;
  bind();
}
const on = (id, fn) => { const el = $(id); if (el) el.addEventListener("click", fn); };
async function run(btn, key, work) {
  if (btn) { btn.disabled = true; btn.dataset.t = btn.textContent; btn.textContent = "En cours…"; }
  const res = await work();
  flash[key] = { ok: !!res.ok, text: res.message || (res.ok ? "C'est fait." : "Échec.") };
  S = await api("/api/settings");
  renderSettings();
  return res;
}
function bind() {
  on("pin-go", async () => {
    try { sessionStorage.setItem("hd-pin", $("pin-in").value.trim()); } catch (e) { /* ignoré */ }
    S = await api("/api/settings");
    flash.pin = S.can_edit ? null : { ok: false, text: "Code incorrect." };
    renderSettings();
  });
  on("tg-change", () => { flash.tgChange = true; renderSettings(); $("tg-token")?.focus(); });
  on("tg-token-go", (e) => run(e.currentTarget, "tg1", async () => {
    const r = await api("/api/settings/telegram/token", { token: $("tg-token").value }); if (r.ok) { flash.tgChange = false; flash.tg2 = null; flash.chats = null; } return r; }));
  on("tg-chat-go", (e) => run(e.currentTarget, "tg2", async () => {
    const r = await api("/api/settings/telegram/chat", {}); flash.chats = r.choose || null; return r; }));
  document.querySelectorAll("[data-chat]").forEach((b) => b.addEventListener("click", () => run(b, "tg2", async () => {
    const r = await api("/api/settings/telegram/chat", { chat_id: b.dataset.chat }); flash.chats = null; return r; })));
  on("tg-test-go", (e) => run(e.currentTarget, "tg3", () => api("/api/settings/telegram/test", {})));
  on("tg-clear", (e) => run(e.currentTarget, "tg1", async () => { const r = await api("/api/settings/telegram/clear", {}); flash.tg2 = flash.tg3 = null; return r; }));
  document.querySelectorAll("[data-ai]").forEach((b) => b.addEventListener("click", () => { aiChoice = b.dataset.ai; flash.ai = null; renderSettings(); }));
  on("ai-eye", () => { const k = $("ai-key"); const show = k.type === "password"; k.type = show ? "text" : "password"; $("ai-eye").textContent = show ? "Masquer" : "Afficher"; });
  on("ai-save", (e) => run(e.currentTarget, "ai", () => api("/api/settings/ai", { provider: aiChoice, key: $("ai-key")?.value || "", model: $("ai-model")?.value || "" })));
  on("ai-clear", (e) => run(e.currentTarget, "ai", () => api("/api/settings/ai/clear", { provider: aiChoice })));
  document.querySelectorAll("#settings .input").forEach((i) => i.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); const go = i.closest(".row")?.querySelector(".btn:not(.ghost)"); if (go) go.click(); }
  }));
}

if (currentTab === "reglages") openSettings();      // arrivée directe sur #reglages
