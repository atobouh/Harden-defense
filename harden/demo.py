"""Données de démonstration : permet de voir (et de présenter) le dashboard SANS lancer les VM.

    python -m harden.demo            ajoute un jeu de données réaliste dans la base
    python -m harden.demo --reset    vide d'abord la base
"""
import random
import sys
from datetime import datetime, timedelta, timezone

from . import config, db, knowledge, parsers

ATTACKS = [  # sid, signature, catégorie, protocole, port, gravité, paquets approximatifs
    (1000001, "HD Scan de ports SYN", "Attempted Information Leak", "TCP", None, 2, 500),
    (1000002, "HD Bruteforce SSH", "Attempted Administrator Privilege Gain", "TCP", 22, 1, 20),
    (1000003, "HD Flood ICMP", "Attempted Denial of Service", "ICMP", None, 2, 40),
    (1000004, "HD Injection SQL (UNION SELECT)", "Web Application Attack", "TCP", 80, 1, 1),
]
DETAILS = {
    "scan": ("2 port(s) ouvert(s) découvert(s), seulement 0/500 sans réponse",
             "scan étouffé : 440/500 ports sans réponse, 2 port(s) ouvert(s) entrevu(s)"),
    "ssh": ("15/15 connexions ont reçu une réponse", "seulement 5/15 connexions ont reçu une réponse"),
    "icmp": ("0% de pertes seulement", "66% des pings perdus"),
    "sqli": ("le serveur a répondu HTTP 200", "aucune réponse du serveur web (connexion coupée)"),
}


def _ts(dt):
    return dt.strftime(parsers.TS_FORMAT)


def populate(conn, now=None, seed=7):
    rnd = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    attacker, target = "192.168.56.102", "192.168.56.101"
    phases = [("ids", now - timedelta(minutes=17)), ("ips", now - timedelta(minutes=6))]
    for mode, start in phases:
        for i, (sid, sig, cat, proto, port, sev, packets) in enumerate(ATTACKS):
            when = start + timedelta(seconds=25 * i)
            key = knowledge.attack_key(sid)
            for engine in ("snort", "suricata"):
                blocked = engine == "suricata" and mode == "ips"
                hits = max(1, int(packets * rnd.uniform(0.9, 1.7))) if sid == 1000001 and blocked else packets
                db.insert_alert(conn, {
                    "ts": _ts(when + timedelta(milliseconds=rnd.randint(1, 900))), "engine": engine, "sid": sid,
                    "signature": sig, "category": cat, "severity": sev, "proto": proto, "src_ip": attacker,
                    "src_port": rnd.randint(30000, 60000) if proto == "TCP" else None, "dst_ip": target,
                    "dst_port": port, "action": "blocked" if blocked else "alert"})
                conn.execute("UPDATE alerts SET hits = ?, last_ts = ? WHERE id = last_insert_rowid()",
                             (hits, _ts(when + timedelta(seconds=3))))
                if key:
                    a = knowledge.local_analysis(sid)
                    conn.execute("INSERT OR IGNORE INTO analyses VALUES (?, ?, ?, ?, ?, ?)",
                                 (sid, a["summary"], a["advice"], a["level"], a["source"], _ts(now)))
            ok_ids, ok_ips = DETAILS[key]
            conn.execute("INSERT INTO attack_results (ts, scenario, mode, success, detail) VALUES (?, ?, ?, ?, ?)",
                         (_ts(when + timedelta(seconds=5)), key, mode, 1 if mode == "ids" else 0,
                          ok_ids if mode == "ids" else ok_ips))
    # quelques sources secondaires, pour que le classement des attaquants soit parlant
    for ip, n, sid in (("192.168.56.130", 2, 1000001), ("192.168.56.77", 1, 1000002)):
        sig = next(a[1] for a in ATTACKS if a[0] == sid)
        for j in range(n):
            db.insert_alert(conn, {"ts": _ts(now - timedelta(minutes=19 - j)), "engine": "suricata", "sid": sid,
                                   "signature": sig, "category": "demo", "severity": 2, "proto": "TCP", "src_ip": ip,
                                   "src_port": 40000 + j, "dst_ip": target, "dst_port": 22, "action": "alert"})
    conn.commit()


def main():
    conn = db.connect(config.DB_PATH)
    if "--reset" in sys.argv:
        for table in ("alerts", "analyses", "attack_results", "offsets"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    populate(conn)
    n = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    print(f"[demo] {n} incidents dans {config.DB_PATH}. Lance le dashboard : python -m harden.dashboard")


if __name__ == "__main__":
    main()
