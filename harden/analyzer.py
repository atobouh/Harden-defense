"""« L'analyste IA » : explique chaque type d'attaque en français clair.

Avec une clé API (ANTHROPIC_API_KEY), l'explication vient de Claude.
Sans clé, ou si l'appel échoue, on utilise le texte écrit à la main (knowledge.py).
Chaque type d'attaque n'est analysé qu'UNE fois : le résultat est gardé en base, donc c'est rapide et peu coûteux.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import config, knowledge

PROMPT = """Tu es un analyste SOC. Une sonde de sécurité réseau vient de déclencher cette alerte :

Règle : {signature}
Catégorie : {category}
Protocole : {proto}, port visé : {dst_port}

Réponds UNIQUEMENT avec un objet JSON de cette forme, en français simple (pour un étudiant) :
{{"summary": "2 phrases max : ce qui se passe et pourquoi c'est dangereux",
  "advice": "1 phrase : l'action concrète à faire",
  "level": un entier de 1 (mineur) à 5 (critique)}}"""


def _ask_claude(alert):
    body = json.dumps({
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": PROMPT.format(
            signature=alert["signature"], category=alert.get("category"),
            proto=alert.get("proto"), dst_port=alert.get("dst_port"))}],
    }).encode()
    req = urllib.request.Request(
        config.ANTHROPIC_API_BASE.rstrip("/") + "/v1/messages", data=body, method="POST",
        headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = json.load(r)["content"][0]["text"]
    data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    level = max(1, min(5, int(data["level"])))
    return {"summary": str(data["summary"]).strip(), "advice": str(data["advice"]).strip(),
            "level": level, "source": "claude"}


def get_analysis(conn, alert):
    """Analyse du type d'attaque (lue en base, ou créée si c'est la première fois)."""
    row = conn.execute("SELECT summary, advice, level, source FROM analyses WHERE sid = ?",
                       (alert["sid"],)).fetchone()
    if row:
        return dict(row)

    result = None
    if config.ANTHROPIC_API_KEY:
        try:
            result = _ask_claude(alert)
        except (urllib.error.URLError, OSError, ValueError, KeyError, AttributeError) as exc:
            print(f"[analyzer] IA indisponible ({exc}); explication locale utilisée.", file=sys.stderr)
    if result is None:
        result = knowledge.local_analysis(alert["sid"])
        if config.ANTHROPIC_API_KEY:
            return result                      # échec temporaire : on réessaiera à la prochaine alerte

    conn.execute("INSERT OR REPLACE INTO analyses (sid, summary, advice, level, source, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?)",
                 (alert["sid"], result["summary"], result["advice"], result["level"], result["source"],
                  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    conn.commit()
    return result
