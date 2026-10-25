"""Configuration : variables d'environnement, avec lecture du fichier .env à la racine du projet."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env_file()


def get(name, default=""):
    return os.environ.get(name, default)


SNORT_ALERT = get("SNORT_ALERT", "/var/log/snort/alert")
SURICATA_EVE = get("SURICATA_EVE", "/var/log/suricata/eve.json")
DB_PATH = get("DB_PATH", str(ROOT / "data" / "harden.db"))
MODE_FILE = get("MODE_FILE", "/run/harden/mode")

TELEGRAM_BOT_TOKEN = get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get("TELEGRAM_CHAT_ID")
TELEGRAM_API_BASE = get("TELEGRAM_API_BASE", "https://api.telegram.org")

ANTHROPIC_API_KEY = get("ANTHROPIC_API_KEY")
ANTHROPIC_API_BASE = get("ANTHROPIC_API_BASE", "https://api.anthropic.com")
ANTHROPIC_MODEL = get("ANTHROPIC_MODEL", "claude-haiku-5-5")

DASHBOARD_HOST = get("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(get("DASHBOARD_PORT", "5000"))
