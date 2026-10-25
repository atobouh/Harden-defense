"""Le collecteur : lit en continu les journaux de Snort et Suricata -> SQLite -> IA -> Telegram.

Lancement :  python -m harden.collector          (tourne en continu)
             python -m harden.collector --once   (lit une fois, puis s'arrête)
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from . import analyzer, config, db, parsers, telegram

NOTIFY_MAX_AGE = timedelta(minutes=2)   # on ne renvoie pas sur Telegram les vieilles alertes (rattrapage)


def read_new_lines(conn, path):
    """Lignes complètes ajoutées au fichier depuis la dernière lecture."""
    try:
        st = os.stat(path)
    except OSError:
        return []
    row = conn.execute("SELECT inode, pos FROM offsets WHERE path = ?", (path,)).fetchone()
    pos = row["pos"] if row and row["inode"] == st.st_ino and row["pos"] <= st.st_size else 0
    try:
        with open(path, "rb") as f:
            f.seek(pos)
            data = f.read()
    except OSError:
        return []
    cut = data.rfind(b"\n")
    if cut < 0:
        return []
    conn.execute("INSERT OR REPLACE INTO offsets (path, inode, pos) VALUES (?, ?, ?)",
                 (path, st.st_ino, pos + cut + 1))
    conn.commit()
    return data[:cut + 1].decode("utf-8", "replace").splitlines()


def handle(conn, alert):
    """Enregistre l'alerte ; si elle est nouvelle : analyse + Telegram. Retourne True si nouvelle."""
    if not db.insert_alert(conn, alert):
        return False
    analysis = analyzer.get_analysis(conn, alert)
    age = datetime.now(timezone.utc) - datetime.strptime(alert["ts"], parsers.TS_FORMAT).replace(tzinfo=timezone.utc)
    if age < NOTIFY_MAX_AGE:
        telegram.notify(alert, analysis)
    return True


def poll(conn):
    new = 0
    for line in read_new_lines(conn, config.SNORT_ALERT):
        a = parsers.parse_snort(line)
        new += bool(a and handle(conn, a))
    for line in read_new_lines(conn, config.SURICATA_EVE):
        a = parsers.parse_suricata(line)
        new += bool(a and handle(conn, a))
    return new


def main():
    conn = db.connect(config.DB_PATH)
    if "--once" in sys.argv:
        print(f"{poll(conn)} nouvelle(s) alerte(s) enregistrée(s).")
        return
    print(f"[collecteur] Snort : {config.SNORT_ALERT}\n[collecteur] Suricata : {config.SURICATA_EVE}\n"
          f"[collecteur] Base : {config.DB_PATH}\n"
          f"[collecteur] Telegram : {'actif' if telegram.enabled() else 'désactivé (pas de token)'}\n"
          f"[collecteur] IA : {'Claude (' + config.ANTHROPIC_MODEL + ')' if config.ANTHROPIC_API_KEY else 'explications locales (pas de clé API)'}",
          flush=True)
    while True:
        n = poll(conn)
        if n:
            print(f"[collecteur] {n} nouvelle(s) alerte(s)", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
