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

AI_PROVIDER = get("AI_PROVIDER")                      # gemini | claude | none (vide = automatique)
GEMINI_API_KEY = get("GEMINI_API_KEY")
GEMINI_API_BASE = get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_MODEL = get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = get("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
TELEGRAM_BOT_NAME = get("TELEGRAM_BOT_NAME")
TELEGRAM_CHAT_NAME = get("TELEGRAM_CHAT_NAME")
ANTHROPIC_API_KEY = get("ANTHROPIC_API_KEY")
ANTHROPIC_API_BASE = get("ANTHROPIC_API_BASE", "https://api.anthropic.com")
ANTHROPIC_MODEL = get("ANTHROPIC_MODEL", "claude-haiku-5-5")

DASHBOARD_HOST = get("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(get("DASHBOARD_PORT", "5000"))


# ---------- Réglages enregistrés par la page « Réglages » ----------
# Fichier privé (data/settings.json, droits 600). Il PASSE AVANT le fichier .env, et il est relu à chaque
# lecture si son contenu a changé : un réglage modifié dans le dashboard est pris en compte tout de suite
# par le collecteur, sans redémarrage.
import json
import tempfile

SETTINGS_FILE = Path(get("SETTINGS_FILE", str(ROOT / "data" / "settings.json")))
EDITABLE = ("AI_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_BOT_NAME", "TELEGRAM_CHAT_NAME")
SECRETS = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN")
_cache = {"stamp": None, "data": {}}


def _file_settings():
    try:
        st = SETTINGS_FILE.stat()
    except OSError:
        _cache.update(stamp=None, data={})
        return _cache["data"]
    stamp = (st.st_mtime_ns, st.st_size)
    if _cache["stamp"] != stamp:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            _cache.update(stamp=stamp, data=data if isinstance(data, dict) else {})
        except (OSError, ValueError):
            _cache.update(stamp=stamp, data={})
    return _cache["data"]


def setting(name, default=""):
    """Valeur d'un réglage : page Réglages > fichier .env / variables d'environnement > valeur par défaut."""
    value = _file_settings().get(name)
    if value not in (None, ""):
        return value
    return globals().get(name, default) or default


def save_settings(changes):
    """Écrit des réglages (valeur None ou "" = effacer). Écriture atomique, droits 600."""
    data = dict(_file_settings())
    for key, value in changes.items():
        if key not in EDITABLE:
            raise KeyError(key)
        if value in (None, ""):
            data.pop(key, None)
        else:
            data[key] = value
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(SETTINGS_FILE.parent), prefix=".settings-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, SETTINGS_FILE)
    _cache["stamp"] = None


def hint(secret):
    """Aperçu d'un secret sans le dévoiler : « …Q660 »."""
    return "…" + secret[-4:] if secret and len(secret) >= 12 else ("•••" if secret else "")
