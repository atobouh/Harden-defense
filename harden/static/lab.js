"use strict";
/* Mode une machine : sélecteur Surveillance/Protection cliquable + bouton « Lancer la démonstration ».
   Tout est caché tant que le laboratoire n'est pas installé (le dashboard seul reste en lecture seule). */
(() => {
  const pin = () => { try { return sessionStorage.getItem("hd-pin") || ""; } catch (e) { return ""; } };
  let lab = null, note = "", noteTimer = null;

  async function call(path, body) {
    const headers = { "Content-Type": "application/json" };
    if (pin()) headers["X-Admin-Pin"] = pin();
    try {
      const r = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
      const j = await r.json().catch(() => ({}));
      return { ok: r.ok && j.ok !== false, message: j.message || (r.ok ? "" : "Action impossible.") };
    } catch (e) {
      return { ok: false, message: "Connexion perdue." };
    }
  }
  function say(text, ms = 6000) {
    note = text; render();
    clearTimeout(noteTimer);
    noteTimer = setTimeout(() => { note = ""; render(); }, ms);
  }

  const STEP_TEXT = ["Test des portes en cours…", "Devinette de mot de passe en cours…", "Saturation de la machine en cours…", "Attaque sur la base de données en cours…"];

  function render() {
    const box = $("demo"), seg = $("seg");
    if (!lab || lab.available === false) { box.hidden = true; delete seg.dataset.live; delete document.body.dataset.lab; return; }
    box.hidden = false;
    document.body.dataset.lab = "1";
    seg.dataset.live = "1";
    seg.querySelectorAll("[data-m]").forEach((el) => { el.setAttribute("role", "button"); el.tabIndex = 0; });
    if (lab.busy) seg.dataset.busy = "1"; else delete seg.dataset.busy;
    const d = lab.demo || {}, go = $("demo-go");
    go.disabled = !!(d.running || lab.busy);
    $("demo-go-label").textContent = d.running ? "Démonstration en cours…" : "Lancer la démonstration";
    const steps = $("demo-steps");
    steps.hidden = !d.running;
    [...steps.children].forEach((li, i) => {
      const cur = Math.max(1, d.step || 1);
      li.className = i + 1 < cur ? "done" : i + 1 === cur ? "now" : "";
    });
    let text = "Les 4 attaques sont lancées pour toi, une par une, depuis une machine attaquante isolée.";
    if (note) text = note;
    else if (lab.busy) text = "Les sondes redémarrent dans le nouveau mode… une dizaine de secondes.";
    else if (lab.error) text = "Le changement de mode a échoué : " + lab.error;
    else if (d.running) text = STEP_TEXT[Math.max(0, (d.step || 1) - 1)] + " Regarde le tableau se remplir.";
    else if (d.finished && d.code === 0) text = lab.mode === "ips" ? "Terminé. Regarde ce qui a été arrêté dans « Attaques »." : "Terminé. En mode Surveillance tout est repéré mais rien n'est bloqué : passe en Protection et relance.";
    $("demo-text").textContent = text;
  }

  async function poll() {
    try {
      const r = await fetch("/api/lab", { cache: "no-store" });
      lab = r.ok ? await r.json() : null;
    } catch (e) { lab = null; }
    render();
  }

  $("seg").addEventListener("click", async (e) => {
    const m = e.target.closest("[data-m]")?.dataset.m;
    if (!m || !lab || lab.available === false || lab.busy || lab.mode === m) return;
    const r = await call("/api/lab/mode", { mode: m });
    if (!r.ok) say(r.message);
    poll();
  });
  $("seg").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.target.click(); } });
  $("demo-go").addEventListener("click", async () => {
    const r = await call("/api/lab/demo", { scenario: "all" });
    if (!r.ok) say(r.message);
    poll();
  });

  poll();
  setInterval(poll, 2000);
})();
