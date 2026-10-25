"""Lecture des journaux : Snort (texte "fast") et Suricata (eve.json).

Les deux sont convertis dans le même format (un dictionnaire), ce qui permet de les comparer.
"""
import json
import re
from datetime import datetime, timedelta, timezone

SNORT_RE = re.compile(
    r"^(?P<mo>\d\d)/(?P<dd>\d\d)(?:/(?P<yy>\d\d))?-(?P<time>\d\d:\d\d:\d\d)\.(?P<us>\d+)\s+"
    r"\[\*\*\]\s+\[(?P<gid>\d+):(?P<sid>\d+):(?P<rev>\d+)\]\s+(?P<msg>.*?)\s+\[\*\*\]\s+"
    r"(?:\[Classification:\s*(?P<cls>[^\]]*)\]\s+)?\[Priority:\s*(?P<prio>\d+)\]\s+"
    r"\{(?P<proto>[A-Za-z0-9]+)\}\s+"
    r"(?P<src>\d+\.\d+\.\d+\.\d+)(?::(?P<sp>\d+))?\s+->\s+(?P<dst>\d+\.\d+\.\d+\.\d+)(?::(?P<dp>\d+))?"
)

_ONE_DAY = timedelta(days=1)
TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime(TS_FORMAT)


def parse_snort(line, now=None):
    """Une ligne du fichier /var/log/snort/alert (format "fast") -> dict, ou None."""
    m = SNORT_RE.match(line.strip())
    if not m:
        return None
    now = now or datetime.now()
    year = 2000 + int(m["yy"]) if m["yy"] else now.year
    naive = datetime(year, int(m["mo"]), int(m["dd"]),
                     *[int(x) for x in m["time"].split(":")], int(m["us"].ljust(6, "0")[:6]))
    if not m["yy"] and naive > now.replace(tzinfo=None) + _ONE_DAY:
        naive = naive.replace(year=year - 1)          # la ligne date de l'an dernier
    return {
        "ts": _utc(naive.astimezone()),               # Snort écrit l'heure locale
        "engine": "snort",
        "sid": int(m["sid"]),
        "signature": m["msg"],
        "category": m["cls"],
        "severity": int(m["prio"]),
        "proto": m["proto"],
        "src_ip": m["src"],
        "src_port": int(m["sp"]) if m["sp"] else None,
        "dst_ip": m["dst"],
        "dst_port": int(m["dp"]) if m["dp"] else None,
        "action": "alert",                            # Snort (IDS) ne bloque jamais
    }


def parse_suricata(line):
    """Une ligne d'eve.json -> dict si c'est une alerte, sinon None."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        e = json.loads(line)
    except ValueError:
        return None
    if e.get("event_type") != "alert" or "alert" not in e:
        return None
    a = e["alert"]
    ts = datetime.strptime(e["timestamp"], "%Y-%m-%dT%H:%M:%S.%f%z")
    return {
        "ts": _utc(ts),
        "engine": "suricata",
        "sid": int(a["signature_id"]),
        "signature": a["signature"],
        "category": a.get("category"),
        "severity": int(a.get("severity", 2)),
        "proto": e.get("proto"),
        "src_ip": e.get("src_ip"),
        "src_port": e.get("src_port"),
        "dst_ip": e.get("dest_ip"),
        "dst_port": e.get("dest_port"),
        "action": "blocked" if a.get("action") == "blocked" else "alert",
    }

