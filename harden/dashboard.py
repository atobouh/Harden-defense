"""Le dashboard web : une page qui lit la base SQLite et se rafraîchit toute seule.

Lancement :  python -m harden.dashboard      puis ouvrir http://IP_UBUNTU:5000
"""
import os
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, send_from_directory

from . import config, db, knowledge, parsers

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


def build_summary(conn, now=None):
    now = now or datetime.now(timezone.utc)

    one = conn.execute(
        "SELECT COUNT(*) AS incidents, COALESCE(SUM(hits), 0) AS packets, "
        "COALESCE(SUM(action = 'blocked'), 0) AS blocked, "
        "COUNT(DISTINCT src_ip) AS attackers FROM alerts").fetchone()
    by_engine = {r["engine"]: r for r in conn.execute(
        "SELECT engine, COUNT(*) AS incidents, COALESCE(SUM(hits), 0) AS packets, "
        "COALESCE(SUM(action = 'blocked'), 0) AS blocked FROM alerts GROUP BY engine")}

    # Chronologie : 1 barre par minute sur les 30 dernières minutes
    start = (now - timedelta(minutes=TIMELINE_MINUTES - 1)).replace(second=0, microsecond=0)
    buckets = {(start + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M"): {"snort": 0, "suricata": 0}
               for i in range(TIMELINE_MINUTES)}
    for r in conn.execute("SELECT substr(ts, 1, 16) AS m, engine, COUNT(*) AS n FROM alerts "
                          "WHERE ts >= ? GROUP BY m, engine", (start.strftime(parsers.TS_FORMAT),)):
        if r["m"] in buckets:
            buckets[r["m"]][r["engine"]] = r["n"]
    timeline = [{"minute": m, **v} for m, v in buckets.items()]

    # Comparaison par type d'attaque : Snort / Suricata / bloquées
    attacks = {k: {"key": k, "name": knowledge.NAMES[k], "snort": 0, "suricata": 0, "blocked": 0,
                   "packets": 0, "ids": None, "ips": None} for k in SCENARIOS}
    for r in conn.execute("SELECT sid, engine, action, COUNT(*) AS n, SUM(hits) AS p FROM alerts "
                          "GROUP BY sid, engine, action"):
        a = attacks.get(knowledge.attack_key(r["sid"]))
        if a:
            a[r["engine"]] += r["n"]
            a["packets"] += r["p"] if r["engine"] == "suricata" else 0
            if r["action"] == "blocked":
                a["blocked"] += r["n"]
    for r in conn.execute(
            "SELECT scenario, mode, success, detail FROM attack_results WHERE id IN "
            "(SELECT MAX(id) FROM attack_results GROUP BY scenario, mode)"):
        if r["scenario"] in attacks and r["mode"] in ("ids", "ips"):
            attacks[r["scenario"]][r["mode"]] = {"success": bool(r["success"]), "detail": r["detail"]}

    top = _rows(conn, "SELECT src_ip, COUNT(*) AS incidents, COALESCE(SUM(hits), 0) AS packets, "
                      "COALESCE(SUM(action = 'blocked'), 0) AS blocked FROM alerts "
                      "GROUP BY src_ip ORDER BY packets DESC LIMIT 5")

    recent = _rows(conn, "SELECT a.id, a.ts, a.last_ts, a.engine, a.sid, a.signature, a.severity, a.proto, "
                         "a.src_ip, a.dst_ip, a.dst_port, a.action, a.hits, "
                         "n.summary, n.advice, n.level, n.source "
                         "FROM alerts a LEFT JOIN analyses n ON n.sid = a.sid ORDER BY a.last_ts DESC, a.id DESC LIMIT 30")
    for r in recent:
        r["name"] = knowledge.attack_name(r["sid"], r["signature"])

    ai = conn.execute("SELECT source FROM analyses ORDER BY created_at DESC LIMIT 1").fetchone()
    return {
        "now": now.strftime(parsers.TS_FORMAT),
        "mode": _mode(conn),
        "totals": {"incidents": one["incidents"], "packets": one["packets"],
                   "blocked": one["blocked"], "detected": one["incidents"] - one["blocked"],
                   "attackers": one["attackers"]},
        "engines": {e: dict(by_engine[e]) if e in by_engine else {"incidents": 0, "packets": 0, "blocked": 0}
                    for e in ("snort", "suricata")},
        "timeline": timeline,
        "attacks": list(attacks.values()),
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


def main():
    print(f"[dashboard] http://localhost:{config.DASHBOARD_PORT}  (depuis Kali : http://IP_UBUNTU:{config.DASHBOARD_PORT})",
          flush=True)
    app.run(host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, threaded=True)


if __name__ == "__main__":
    main()
