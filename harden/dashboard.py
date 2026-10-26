"""Le dashboard web : une page qui lit la base SQLite et se rafraîchit toute seule.

Lancement :  python -m harden.dashboard      puis ouvrir http://IP_UBUNTU:5000
"""
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory

from . import analyzer, config, db, knowledge, labctl, parsers, telegram

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app = Flask(__name__, static_folder=STATIC, static_url_path="/static")

SCENARIOS = ["scan", "ssh", "icmp", "sqli"]
TIMELINE_MINUTES = 30


def _conn():
    return db.connect(config.DB_PATH)


def _mode(conn=None):
    """Mode courant : lu dans le fichier écrit par lab.sh, sinon déduit de la dernière alerte Suricata."""
    try:
        with open(config.MODE_FILE, encoding="utf-8") as f:
            value = f.read().strip()
        if value in ("ids", "ips", "stopped"):
            return value
    except OSError:
        pass
    if conn is not None:
        row = conn.execute("SELECT action FROM alerts WHERE engine = 'suricata' ORDER BY last_ts DESC LIMIT 1").fetchone()
        if row:
            return "ips" if row["action"] == "blocked" else "ids"
    return "unknown"


def _rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def _attack_states(conn):
    """État de chaque attaque, du point de vue de quelqu'un qui n'y connaît rien :
       waiting = pas encore vue · passed = repérée mais pas arrêtée · stopped = arrêtée."""
    attacks = {k: {"key": k, "name": knowledge.NAMES[k], "state": "waiting", "snort": 0, "suricata": 0,
                   "stopped": 0, "passed": 0, "packets": 0, "last_ts": None, "ids": None, "ips": None}
               for k in SCENARIOS}
    latest_suricata = {}
    for r in conn.execute("SELECT sid, engine, action, COUNT(*) AS n, SUM(hits) AS p, MAX(last_ts) AS last "
                          "FROM alerts GROUP BY sid, engine, action"):
        a = attacks.get(knowledge.attack_key(r["sid"]))
        if not a:
            continue
        a[r["engine"]] += r["n"]
        a["last_ts"] = max(filter(None, [a["last_ts"], r["last"]]))
        if r["engine"] == "suricata":
            a["packets"] += r["p"]
            a["stopped" if r["action"] == "blocked" else "passed"] += r["n"]
            if r["last"] > latest_suricata.get(a["key"], ("", ""))[0]:
                latest_suricata[a["key"]] = (r["last"], r["action"])
    for key, a in attacks.items():
        if key in latest_suricata:
            a["state"] = "stopped" if latest_suricata[key][1] == "blocked" else "passed"
        elif a["snort"]:
            a["state"] = "passed"          # seule Snort l'a vue : elle l'a signalée, rien de plus
    for r in conn.execute(
            "SELECT scenario, mode, success, detail FROM attack_results WHERE id IN "
            "(SELECT MAX(id) FROM attack_results GROUP BY scenario, mode)"):
        if r["scenario"] in attacks and r["mode"] in ("ids", "ips"):
            attacks[r["scenario"]][r["mode"]] = {"success": bool(r["success"]), "detail": r["detail"]}
    return list(attacks.values())


def build_summary(conn, now=None):
    now = now or datetime.now(timezone.utc)

    tot = conn.execute(
        "SELECT COALESCE(SUM(action = 'blocked'), 0) AS stopped, COALESCE(SUM(action != 'blocked'), 0) AS passed "
        "FROM alerts WHERE engine = 'suricata'").fetchone()
    sources = conn.execute("SELECT COUNT(DISTINCT src_ip) FROM alerts").fetchone()[0]
    by_engine = {r["engine"]: r for r in conn.execute(
        "SELECT engine, COUNT(*) AS incidents, COALESCE(SUM(action = 'blocked'), 0) AS blocked FROM alerts GROUP BY engine")}

    # Chronologie : 1 barre par minute sur les 30 dernières minutes, selon l'issue (arrêtée / passée)
    start = (now - timedelta(minutes=TIMELINE_MINUTES - 1)).replace(second=0, microsecond=0)
    buckets = {(start + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M"): {"stopped": 0, "passed": 0}
               for i in range(TIMELINE_MINUTES)}
    for r in conn.execute("SELECT substr(ts, 1, 16) AS m, action, COUNT(*) AS n FROM alerts "
                          "WHERE engine = 'suricata' AND ts >= ? GROUP BY m, action", (start.strftime(parsers.TS_FORMAT),)):
        if r["m"] in buckets:
            buckets[r["m"]]["stopped" if r["action"] == "blocked" else "passed"] += r["n"]
    timeline = [{"minute": m, **v} for m, v in buckets.items()]

    top = _rows(conn, "SELECT src_ip, MAX(n) AS attempts, SUM(b) AS stopped FROM ("
                      "SELECT src_ip, engine, COUNT(*) AS n, SUM(action = 'blocked') AS b FROM alerts "
                      "GROUP BY src_ip, engine) GROUP BY src_ip ORDER BY attempts DESC LIMIT 3")

    recent = _rows(conn, "SELECT a.id, a.ts, a.last_ts, a.engine, a.sid, a.signature, a.severity, a.proto, "
                         "a.src_ip, a.src_port, a.dst_ip, a.dst_port, a.action, a.hits, "
                         "n.summary, n.advice, n.level, n.source "
                         "FROM alerts a LEFT JOIN analyses n ON n.sid = a.sid ORDER BY a.last_ts DESC, a.id DESC LIMIT 30")
    for r in recent:
        r["key"] = knowledge.attack_key(r["sid"])
        r["name"] = knowledge.attack_name(r["sid"], r["signature"])

    ai = conn.execute("SELECT source FROM analyses ORDER BY created_at DESC LIMIT 1").fetchone()
    return {
        "now": now.strftime(parsers.TS_FORMAT),
        "mode": _mode(conn),
        "totals": {"stopped": tot["stopped"], "passed": tot["passed"], "sources": sources},
        "engines": {e: {"incidents": by_engine[e]["incidents"], "blocked": by_engine[e]["blocked"]}
                    if e in by_engine else {"incidents": 0, "blocked": 0} for e in ("snort", "suricata")},
        "timeline": timeline,
        "attacks": _attack_states(conn),
        "top_attackers": top,
        "recent": recent,
        "ai_source": ai["source"] if ai else None,
    }


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/api/summary")
def summary():
    conn = _conn()
    try:
        return jsonify(build_summary(conn))
    finally:
        conn.close()


@app.post("/api/attack_result")
def attack_result():
    """Reçoit le verdict envoyé par le script d'attaque lancé depuis Kali."""
    data = request.get_json(silent=True) or {}
    scenario = data.get("scenario")
    conn = _conn()
    mode = _mode(conn)
    if scenario not in SCENARIOS or mode not in ("ids", "ips"):
        conn.close()
        return jsonify(error="scénario inconnu ou labo non démarré (lance lab.sh ids|ips)"), 400
    try:
        conn.execute("INSERT INTO attack_results (ts, scenario, mode, success, detail) VALUES (?, ?, ?, ?, ?)",
                     (datetime.now(timezone.utc).strftime(parsers.TS_FORMAT), scenario, mode,
                      1 if data.get("success") else 0, str(data.get("detail", ""))[:300]))
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True, mode=mode)


# ---------- page « Réglages » ----------
# Sécurité : le dashboard n'a pas de comptes. Les réglages (clés, token) ne peuvent donc être modifiés que
#   - depuis la machine qui fait tourner l'application (http://localhost:5000), ou
#   - à distance avec le CODE affiché dans le terminal au démarrage.
# Et les secrets ne sont JAMAIS renvoyés au navigateur (seulement « configuré » et les 4 derniers caractères).
ADMIN_PIN = f"{secrets.randbelow(10 ** 6):06d}"
LOCAL_ADDRS = ("127.0.0.1", "::1")
_pin_fail = {"count": 0, "until": 0.0}


def _is_local():
    return request.remote_addr in LOCAL_ADDRS or request.remote_addr in config.TRUSTED_ADDRS


def _check_access():
    """None si autorisé, sinon (message, code HTTP)."""
    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.host:
        return "Origine refusée.", 403
    if _is_local():
        return None
    if time.time() < _pin_fail["until"]:
        return "Trop d'essais. Patiente une minute.", 429
    if hmac.compare_digest(request.headers.get("X-Admin-Pin", ""), ADMIN_PIN):
        _pin_fail["count"] = 0
        return None
    _pin_fail["count"] += 1
    if _pin_fail["count"] >= 5:
        _pin_fail.update(count=0, until=time.time() + 60)
    return "Code de sécurité manquant ou incorrect (il est affiché dans le terminal où tourne l'application).", 403


def _can_edit():
    return _check_access() is None if _is_local() or request.headers.get("X-Admin-Pin") else False


def _guard():
    """Garde pour les routes qui modifient : retourne (corps JSON, None) ou (None, réponse d'erreur)."""
    problem = _check_access()
    if problem:
        return None, (jsonify(ok=False, message=problem[0]), problem[1])
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify(ok=False, message="Requête invalide."), 400)
    return data, None


def _clean(value):
    return re.sub(r"\s+", "", str(value or "")).strip("\"'")


@app.get("/api/settings")
def settings_view():
    """État des réglages, sans aucun secret."""
    provider = analyzer.active_provider()
    key_name = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}.get(provider)
    conn = _conn()
    try:
        try:
            status = json.loads(db.get_state(conn, "ai_status", "null"))
        except ValueError:
            status = None
        pending = analyzer.Worker(conn).pending_count()
    finally:
        conn.close()
    tg_token = config.setting("TELEGRAM_BOT_TOKEN")
    return jsonify(
        can_edit=_can_edit(), needs_pin=not _is_local(),
        ai={"provider": provider, "choice": config.setting("AI_PROVIDER") or "",
            "key_set": bool(key_name and config.setting(key_name)),
            "key_hint": config.hint(config.setting(key_name)) if key_name else "",
            "has_gemini_key": bool(config.setting("GEMINI_API_KEY")), "has_claude_key": bool(config.setting("ANTHROPIC_API_KEY")),
            "model": (analyzer.models_for(provider) or [""])[0],
            "models": {"gemini": list(analyzer.GEMINI_MODELS), "claude": list(analyzer.CLAUDE_MODELS)},
            "status": status, "pending": pending, "batch_size": analyzer.BATCH_SIZE, "max_rpm": analyzer.MAX_RPM},
        telegram={"token_set": bool(tg_token), "token_hint": config.hint(tg_token),
                  "bot": config.setting("TELEGRAM_BOT_NAME"), "chat_set": bool(config.setting("TELEGRAM_CHAT_ID")),
                  "chat_name": config.setting("TELEGRAM_CHAT_NAME")})


@app.post("/api/settings/ai")
def settings_ai():
    """Teste la clé (un vrai petit appel) et ne l'enregistre que si elle fonctionne."""
    data, error = _guard()
    if error:
        return error
    provider = data.get("provider")
    if provider == "none":
        config.save_settings({"AI_PROVIDER": "none"})
        return jsonify(ok=True, message="IA désactivée : les explications intégrées sont utilisées.")
    if provider not in ("gemini", "claude"):
        return jsonify(ok=False, message="Fournisseur inconnu."), 400
    key_name = "GEMINI_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
    model_name = "GEMINI_MODEL" if provider == "gemini" else "ANTHROPIC_MODEL"
    key = _clean(data.get("key")) or config.setting(key_name)
    if not key:
        return jsonify(ok=False, message="Colle d'abord ta clé."), 400
    if len(key) < 20 or len(key) > 300:
        return jsonify(ok=False, message="Cette clé n'a pas la bonne longueur. Copie-la en entier."), 400
    model = _clean(data.get("model")) or None
    if model and not re.fullmatch(r"[A-Za-z0-9._-]{3,60}", model):
        return jsonify(ok=False, message="Nom de modèle invalide."), 400
    result = analyzer.test_provider(provider, key, model)
    if not result["ok"]:
        return jsonify(ok=False, message=result["message"])
    config.save_settings({"AI_PROVIDER": provider, key_name: key, model_name: result["model"]})
    return jsonify(ok=True, model=result["model"], ms=result["ms"], sample=result["sample"],
                   message=f"Connecté : {result['model']} a répondu en {result['ms'] / 1000:.1f} s.")


@app.post("/api/settings/ai/clear")
def settings_ai_clear():
    data, error = _guard()
    if error:
        return error
    which = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}.get(data.get("provider"))
    if not which:
        return jsonify(ok=False, message="Fournisseur inconnu."), 400
    config.save_settings({which: ""})
    return jsonify(ok=True, message="Clé supprimée.")


@app.post("/api/settings/telegram/token")
def settings_tg_token():
    data, error = _guard()
    if error:
        return error
    token = _clean(data.get("token"))
    if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token):
        return jsonify(ok=False, message="Ça ne ressemble pas à un token. Il ressemble à 123456789:AAH… (avec un « : » au milieu).")
    try:
        bot = telegram.get_me(token)
    except telegram.TelegramError as exc:
        return jsonify(ok=False, message=str(exc))
    changed = token != config.setting("TELEGRAM_BOT_TOKEN")
    config.save_settings({"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_BOT_NAME": bot,
                          **({"TELEGRAM_CHAT_ID": "", "TELEGRAM_CHAT_NAME": ""} if changed else {})})
    return jsonify(ok=True, bot=bot, message=f"Connecté au bot @{bot}.")


@app.post("/api/settings/telegram/chat")
def settings_tg_chat():
    """Trouve la conversation de l'utilisateur (il doit avoir envoyé /start à son bot)."""
    data, error = _guard()
    if error:
        return error
    token = config.setting("TELEGRAM_BOT_TOKEN")
    if not token:
        return jsonify(ok=False, message="Connecte d'abord ton bot (étape 1)."), 400
    try:
        chats = telegram.find_chats(token)
    except telegram.TelegramError as exc:
        return jsonify(ok=False, message=str(exc))
    chosen = data.get("chat_id")
    if chosen is not None:
        chats = [c for c in chats if str(c["id"]) == str(chosen)]
    if not chats:
        return jsonify(ok=False, message="Rien reçu pour l'instant. Ouvre ton bot dans Telegram, envoie-lui « /start », puis réessaie.")
    if len(chats) > 1:
        return jsonify(ok=True, choose=chats, message="Plusieurs conversations trouvées : choisis la tienne.")
    config.save_settings({"TELEGRAM_CHAT_ID": str(chats[0]["id"]), "TELEGRAM_CHAT_NAME": chats[0]["name"]})
    return jsonify(ok=True, name=chats[0]["name"], message=f"Compte trouvé : {chats[0]['name']}.")


@app.post("/api/settings/telegram/test")
def settings_tg_test():
    data, error = _guard()
    if error:
        return error
    if not telegram.enabled():
        return jsonify(ok=False, message="Termine d'abord les étapes 1 et 2."), 400
    sent = telegram.send("✅ <b>Harden Defense</b> : le bot Telegram est bien relié. Les alertes arriveront ici.")
    return jsonify(ok=sent, message="Message envoyé : regarde ton téléphone." if sent else "Telegram n'a pas accepté le message. Refais l'étape 2.")


@app.post("/api/settings/telegram/clear")
def settings_tg_clear():
    data, error = _guard()
    if error:
        return error
    config.save_settings({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "TELEGRAM_BOT_NAME": "", "TELEGRAM_CHAT_NAME": ""})
    return jsonify(ok=True, message="Telegram déconnecté.")


# ---------- pilotage du laboratoire (mode une machine) ----------
# Le dashboard n'a pas les droits système : il transmet des ordres au « chef d'orchestre » (labd) via un socket réservé.
@app.get("/api/lab")
def lab_status():
    r = labctl.call({"cmd": "status"})
    r["can_edit"] = _can_edit()
    return jsonify(r)


@app.post("/api/lab/mode")
def lab_mode():
    data, error = _guard()
    if error:
        return error
    r = labctl.call({"cmd": "mode", "value": data.get("mode")})
    return jsonify(r), 200 if r.get("ok") else (503 if r.get("available") is False else 409)


@app.post("/api/lab/demo")
def lab_demo():
    data, error = _guard()
    if error:
        return error
    r = labctl.call({"cmd": "demo", "scenario": data.get("scenario", "all")})
    return jsonify(r), 200 if r.get("ok") else (503 if r.get("available") is False else 409)


def main():
    pin_file = os.environ.get("PIN_FILE")          # permet à la commande « sudo harden pin » de l'afficher
    if pin_file:
        with open(os.open(pin_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            f.write(ADMIN_PIN + "\n")
    print(f"[dashboard] http://localhost:{config.DASHBOARD_PORT}  (depuis un autre appareil : http://IP_UBUNTU:{config.DASHBOARD_PORT})\n"
          f"[dashboard] Réglages (clés, Telegram) : http://localhost:{config.DASHBOARD_PORT}/#reglages\n"
          f"[dashboard] Pour les modifier depuis un autre appareil, le code est : {ADMIN_PIN}", flush=True)
    app.run(host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, threaded=True)


if __name__ == "__main__":
    main()
