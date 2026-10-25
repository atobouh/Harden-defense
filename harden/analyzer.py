"""« L'analyste IA » : explique chaque type d'attaque en français clair, PAR LOT.

Principe (à expliquer en soutenance) :
  1. Une alerte arrive : elle est enregistrée et envoyée tout de suite, avec le texte intégré (knowledge.py).
     Rien n'attend l'IA.
  2. Un petit « travailleur » regarde régulièrement quels types d'attaque n'ont pas encore d'explication de l'IA.
     Il les regroupe (jusqu'à 20) dans UNE seule requête, ce qui respecte la limite gratuite
     (15 requêtes par minute et par modèle chez Google ; on se limite à 8).
  3. La réponse (du JSON) est vérifiée, puis rangée en base : le dashboard affiche alors l'explication de l'IA.
  4. Si Google dit « trop de requêtes », on attend, on essaie un modèle de secours (qui a son propre compteur),
     et en dernier recours on garde le texte intégré. L'application ne tombe jamais en panne à cause de l'IA.
"""
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone

from . import config, db, knowledge

BATCH_SIZE = 20          # alertes par requête
MAX_RPM = 8              # requêtes par minute (la limite gratuite de Google est 15)
TICK_SECONDS = 10        # le travailleur se réveille toutes les 10 s
GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash")
CLAUDE_MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")

STYLE = ("Tu es un analyste SOC qui explique des alertes à un étudiant non technique. "
         "Pour CHAQUE alerte ci-dessous, réponds en français simple, en vouvoyant, sans dire « notre ». "
         "summary = 2 phrases maximum : ce qui se passe et pourquoi c'est dangereux. "
         "advice = 1 phrase : l'action concrète à faire. "
         "level = un entier de 1 (mineur) à 5 (critique). Garde exactement le même id que l'alerte.")

SCHEMA = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "id": {"type": "INTEGER"}, "summary": {"type": "STRING"}, "advice": {"type": "STRING"}, "level": {"type": "INTEGER"}},
    "required": ["id", "summary", "advice", "level"]}}


class RateLimited(Exception):
    def __init__(self, retry_after=60):
        super().__init__(f"limite atteinte, réessayer dans {retry_after:.0f} s")
        self.retry_after = retry_after


class ProviderError(Exception):
    """Erreur du fournisseur. `kind` : auth (clé refusée), model (modèle indisponible), other (temporaire)."""
    def __init__(self, message, kind="other"):
        super().__init__(message)
        self.kind = kind


# ---------- choix du fournisseur ----------
def active_provider():
    """'gemini', 'claude' ou 'none'."""
    choice = (config.setting("AI_PROVIDER") or "").lower()
    if choice == "none":
        return "none"
    if choice == "gemini" or (not choice and config.setting("GEMINI_API_KEY")):
        return "gemini" if config.setting("GEMINI_API_KEY") else "none"
    if choice == "claude" or (not choice and config.setting("ANTHROPIC_API_KEY")):
        return "claude" if config.setting("ANTHROPIC_API_KEY") else "none"
    return "none"


def models_for(provider):
    if provider == "gemini":
        primary = config.setting("GEMINI_MODEL") or GEMINI_MODELS[0]
        backup = config.setting("GEMINI_FALLBACK_MODEL")
        return [m for m in dict.fromkeys([primary, backup]) if m]
    if provider == "claude":
        return [config.setting("ANTHROPIC_MODEL") or CLAUDE_MODELS[0]]
    return []


# ---------- le message envoyé à l'IA (jamais d'adresse IP : seulement la règle, le protocole et le port) ----------
def build_prompt(items):
    payload = [{"id": i["id"], "regle": i["signature"], "categorie": i.get("category"),
                "protocole": i.get("proto"), "port": i.get("dst_port")} for i in items]
    return STYLE + "\n\nAlertes :\n" + json.dumps(payload, ensure_ascii=False)


def parse_batch(text, expected_ids):
    """Lit la réponse de l'IA. Retourne {id: {summary, advice, level}} pour les entrées VALIDES seulement."""
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise ProviderError("réponse sans liste JSON")
    try:
        raw = json.loads(match.group(0))
    except ValueError as exc:
        raise ProviderError(f"JSON illisible : {exc}")
    out = {}
    for entry in raw if isinstance(raw, list) else []:
        try:
            sid = int(entry["id"])
            summary, advice = str(entry["summary"]).strip(), str(entry["advice"]).strip()
            level = max(1, min(5, int(entry["level"])))
        except (KeyError, TypeError, ValueError):
            continue
        if sid in expected_ids and summary and advice:
            out[sid] = {"summary": summary, "advice": advice, "level": level}
    return out


# ---------- appels réseau ----------
def _post(url, headers, body, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={**headers, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            err = json.loads(raw).get("error", {})
        except ValueError:
            err = {}
        message = err.get("message") or raw[:200] if isinstance(err, dict) else raw[:200]
        if exc.code == 429:
            delay = 60.0
            for detail in (err.get("details", []) if isinstance(err, dict) else []):
                m = re.match(r"([\d.]+)s", str(detail.get("retryDelay", "")))
                if m:
                    delay = float(m.group(1)) + 1
            raise RateLimited(delay)
        if exc.code in (400, 401, 403) and re.search(r"api key|api_key|authentication|permission|invalid x-api-key", message, re.I):
            raise ProviderError("clé refusée par le fournisseur", "auth")
        if exc.code in (400, 401, 403):
            raise ProviderError(message[:160], "auth" if exc.code != 400 else "other")
        if exc.code == 404:
            raise ProviderError("modèle indisponible", "model")
        raise ProviderError(f"erreur {exc.code}", "other")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ProviderError(f"réseau injoignable ({exc})", "other")


def call_gemini(model, items, key):
    d = _post(f"{config.setting('GEMINI_API_BASE').rstrip('/')}/models/{model}:generateContent",
              {"x-goog-api-key": key},
              {"contents": [{"parts": [{"text": build_prompt(items)}]}],
               "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0.2}})
    try:
        return parse_batch(d["candidates"][0]["content"]["parts"][0]["text"], {i["id"] for i in items})
    except (KeyError, IndexError, TypeError):
        raise ProviderError("réponse vide ou bloquée")


def call_claude(model, items, key):
    d = _post(config.setting("ANTHROPIC_API_BASE").rstrip("/") + "/v1/messages",
              {"x-api-key": key, "anthropic-version": "2023-06-01"},
              {"model": model, "max_tokens": 4000,
               "messages": [{"role": "user", "content": build_prompt(items) + "\n\nRéponds UNIQUEMENT avec la liste JSON."}]})
    try:
        return parse_batch(d["content"][0]["text"], {i["id"] for i in items})
    except (KeyError, IndexError, TypeError):
        raise ProviderError("réponse vide")


def call_provider(provider, model, items, key):
    return (call_gemini if provider == "gemini" else call_claude)(model, items, key)


def explain_error(exc):
    """Message simple, en français, pour la page Réglages."""
    if isinstance(exc, RateLimited):
        return "Limite gratuite atteinte pour le moment. L'application réessaie toute seule dans une minute."
    kind = getattr(exc, "kind", "other")
    if kind == "auth":
        return "Clé refusée. Vérifie qu'elle est copiée en entier, sans espace."
    if kind == "model":
        return "Ce modèle n'est pas disponible sur ton compte. Choisis-en un autre dans les options avancées."
    return f"Échec : {exc}"


def test_provider(provider, key, model=None):
    """Essai réel et minuscule (1 alerte), pour valider une clé avant de l'enregistrer."""
    model = model or models_for(provider)[0]
    sample = [{"id": 1, "signature": "HD Scan de ports SYN", "category": "Attempted Information Leak",
               "proto": "TCP", "dst_port": None}]
    started = time.time()
    try:
        result = call_provider(provider, model, sample, key)
    except (RateLimited, ProviderError) as exc:
        return {"ok": False, "message": explain_error(exc)}
    if 1 not in result:
        return {"ok": False, "message": "L'IA a répondu, mais pas dans le bon format. Essaie un autre modèle."}
    return {"ok": True, "model": model, "ms": int((time.time() - started) * 1000), "sample": result[1]["summary"]}


# ---------- texte intégré : toujours disponible, jamais d'attente ----------
def get_analysis(conn, alert):
    """Explication du type d'attaque : celle en base, sinon le texte intégré (rangé en base, remplaçable par l'IA)."""
    row = conn.execute("SELECT summary, advice, level, source FROM analyses WHERE sid = ?", (alert["sid"],)).fetchone()
    if row:
        return dict(row)
    result = knowledge.local_analysis(alert["sid"])
    _store(conn, alert["sid"], result)
    return result


def _store(conn, sid, result):
    conn.execute("INSERT OR REPLACE INTO analyses (sid, summary, advice, level, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (sid, result["summary"], result["advice"], result["level"], result["source"],
                  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    conn.commit()


# ---------- le travailleur par lots ----------
class Worker:
    def __init__(self, conn, clock=time.time):
        self.conn, self.clock = conn, clock
        self.sent = deque()                 # horodatages des requêtes de la dernière minute
        self.model_wait = {}                # modèle -> instant avant lequel on ne le rappelle pas
        self.wait_until = 0.0               # pause globale après un échec complet
        self.failures = 0
        self.attempts = {}                  # sid -> nombre d'essais ratés (évite de boucler sur un cas impossible)

    def pending(self, limit=BATCH_SIZE):
        """Types d'attaque vus, mais sans explication de l'IA (manquante, ou seulement le texte intégré)."""
        now = self.clock()
        rows = self.conn.execute(
            "SELECT a.sid AS id, MAX(a.signature) AS signature, MAX(a.category) AS category, MAX(a.proto) AS proto, "
            "MAX(a.dst_port) AS dst_port FROM alerts a LEFT JOIN analyses n ON n.sid = a.sid "
            "WHERE n.sid IS NULL OR n.source = 'local' GROUP BY a.sid ORDER BY MIN(a.id)").fetchall()
        items = [dict(r) for r in rows if self.attempts.get(r["id"], (0, 0))[1] <= now]
        return items[:limit]

    def pending_count(self):
        return self.conn.execute("SELECT COUNT(DISTINCT a.sid) FROM alerts a LEFT JOIN analyses n ON n.sid = a.sid "
                                 "WHERE n.sid IS NULL OR n.source = 'local'").fetchone()[0]

    def _budget_ok(self):
        now = self.clock()
        while self.sent and now - self.sent[0] > 60:
            self.sent.popleft()
        return len(self.sent) < MAX_RPM

    def _status(self, ok, model=None, error=None, count=0):
        db.set_state(self.conn, "ai_status", json.dumps({
            "ok": ok, "model": model, "error": error, "count": count,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}))

    def run_once(self):
        """Un passage. Retourne le nombre d'explications obtenues de l'IA."""
        provider = active_provider()
        if provider == "none" or self.clock() < self.wait_until or not self._budget_ok():
            return 0
        items = self.pending()
        if not items:
            return 0
        key = config.setting("GEMINI_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY")
        last_error = None
        for model in models_for(provider):
            if self.clock() < self.model_wait.get(model, 0):
                continue
            self.sent.append(self.clock())
            try:
                answers = call_provider(provider, model, items, key)
            except RateLimited as exc:
                self.model_wait[model] = self.clock() + exc.retry_after      # ce modèle se repose ; on tente le suivant
                last_error = exc
                continue
            except ProviderError as exc:
                last_error = exc
                if exc.kind == "auth":
                    break                                                    # inutile d'insister avec une mauvaise clé
                continue
            for item in items:
                if item["id"] in answers:
                    answers[item["id"]]["source"] = provider
                    _store(self.conn, item["id"], answers[item["id"]])
                    self.attempts.pop(item["id"], None)
                else:                                                        # l'IA a sauté cette alerte : on réessaiera plus tard
                    n = self.attempts.get(item["id"], (0, 0))[0] + 1
                    self.attempts[item["id"]] = (n, self.clock() + min(900, 60 * 2 ** n))
            self.failures = 0
            self._status(True, model, count=len(answers))
            return len(answers)
        self.failures += 1
        self.wait_until = self.clock() + min(300, 20 * 2 ** self.failures)
        self._status(False, error=explain_error(last_error) if last_error else "Aucune réponse", count=0)
        print(f"[analyseur] IA indisponible : {last_error}. Texte intégré conservé, nouvel essai dans "
              f"{self.wait_until - self.clock():.0f} s.", file=sys.stderr, flush=True)
        return 0


def start_worker(db_path):
    """Lance le travailleur dans un fil séparé (utilisé par le collecteur)."""
    def loop():
        worker = Worker(db.connect(db_path))
        while True:
            try:
                worker.run_once()
            except Exception as exc:                      # le travailleur ne doit jamais s'arrêter
                print(f"[analyseur] erreur inattendue : {exc}", file=sys.stderr, flush=True)
            time.sleep(TICK_SECONDS)
    threading.Thread(target=loop, daemon=True, name="analyse-ia").start()
