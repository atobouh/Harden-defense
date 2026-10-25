"""Base de données SQLite : un simple fichier, aucune installation de serveur."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,            -- date UTC ISO 8601
    engine    TEXT    NOT NULL,            -- 'snort' (IDS) ou 'suricata' (IPS)
    sid       INTEGER NOT NULL,            -- identifiant de la règle
    signature TEXT    NOT NULL,
    category  TEXT,
    severity  INTEGER NOT NULL DEFAULT 2,  -- 1 = élevée, 2 = moyenne, 3 = faible
    proto     TEXT,
    src_ip    TEXT,
    src_port  INTEGER,
    dst_ip    TEXT,
    dst_port  INTEGER,
    action    TEXT    NOT NULL,            -- 'alert' (détectée) ou 'blocked' (bloquée)
    hits      INTEGER NOT NULL DEFAULT 1,  -- nombre de paquets regroupés dans cet incident
    last_ts   TEXT,                        -- date du dernier paquet de l'incident
    UNIQUE (engine, ts, sid, src_ip, src_port, dst_ip, dst_port)
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts  ON alerts (ts);
CREATE INDEX IF NOT EXISTS idx_alerts_sid ON alerts (sid);

CREATE TABLE IF NOT EXISTS analyses (      -- explication de chaque type d'attaque
    sid        INTEGER PRIMARY KEY,
    summary    TEXT NOT NULL,
    advice     TEXT NOT NULL,
    level      INTEGER NOT NULL,           -- gravité 1 à 5
    source     TEXT NOT NULL,              -- 'claude' (IA) ou 'local'
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attack_results ( -- ce que Kali a observé de son côté
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    scenario TEXT NOT NULL,                 -- scan, ssh, icmp, sqli
    mode     TEXT NOT NULL,                 -- ids ou ips
    success  INTEGER NOT NULL,              -- 1 = l'attaque est passée, 0 = bloquée
    detail   TEXT
);

CREATE TABLE IF NOT EXISTS offsets (        -- où le collecteur s'est arrêté dans chaque log
    path  TEXT PRIMARY KEY,
    inode INTEGER NOT NULL,
    pos   INTEGER NOT NULL
);
"""


def connect(path):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


INSERT_ALERT = """
INSERT OR IGNORE INTO alerts
 (ts, engine, sid, signature, category, severity, proto, src_ip, src_port, dst_ip, dst_port, action, last_ts)
VALUES
 (:ts, :engine, :sid, :signature, :category, :severity, :proto, :src_ip, :src_port, :dst_ip, :dst_port, :action, :ts)
"""

GROUP_SECONDS = 30   # des alertes identiques à moins de 30 s d'écart = un seul incident (les clients retransmettent)


def insert_alert(conn, alert):
    """Enregistre l'alerte. Si c'est la suite d'un incident en cours (même moteur, même règle,
    même source, même action, < 10 s), on augmente simplement son compteur de paquets.
    Retourne True seulement pour un NOUVEL incident."""
    prev = conn.execute(
        "SELECT id FROM alerts WHERE engine = ? AND sid = ? AND src_ip = ? AND action = ? "
        "AND last_ts >= strftime('%Y-%m-%dT%H:%M:%fZ', ?, ?) ORDER BY id DESC LIMIT 1",
        (alert["engine"], alert["sid"], alert["src_ip"], alert["action"],
         alert["ts"], f"-{GROUP_SECONDS} seconds")).fetchone()
    if prev:
        conn.execute("UPDATE alerts SET hits = hits + 1, last_ts = MAX(last_ts, ?) WHERE id = ?",
                     (alert["ts"], prev["id"]))
        conn.commit()
        return False
    cur = conn.execute(INSERT_ALERT, alert)
    conn.commit()
    return cur.rowcount == 1
