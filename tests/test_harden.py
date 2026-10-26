"""Tests automatiques :  python3 -m unittest discover -s tests -v   (aucune dépendance, aucun réseau réel)"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path  # noqa: E402

from harden import analyzer, collector, config, db, labctl, labd, parsers, telegram  # noqa: E402

try:
    from harden import dashboard
except ImportError:          # Flask pas installé : les tests du dashboard sont ignorés
    dashboard = None

SNORT_LINE = ("10/25-17:40:59.002045  [**] [1:1000001:1] HD Scan de ports SYN [**] "
              "[Classification: Attempted Information Leak] [Priority: 2] {TCP} 10.77.0.2:33773 -> 10.77.0.1:17")
SNORT_ICMP = ("10/25-17:41:00.100000  [**] [1:1000003:1] HD Flood ICMP [**] "
              "[Classification: Attempted Denial of Service] [Priority: 2] {ICMP} 10.77.0.2 -> 10.77.0.1")
EVE_LINE = json.dumps({
    "timestamp": "2026-10-25T17:44:20.576999+0000", "event_type": "alert", "src_ip": "10.77.0.2", "src_port": 51424,
    "dest_ip": "10.77.0.1", "dest_port": 80, "proto": "TCP",
    "alert": {"action": "blocked", "signature_id": 1000004, "signature": "HD Injection SQL (UNION SELECT)",
              "category": "Web Application Attack", "severity": 1}})


from harden import config as _config  # noqa: E402
_TMP = tempfile.mkdtemp()
_config.SETTINGS_FILE = Path(_TMP) / "settings.json"      # les tests n'écrivent jamais dans data/settings.json


def reset_settings():
    try:
        _config.SETTINGS_FILE.unlink()
    except FileNotFoundError:
        pass
    _config._cache["stamp"] = None


class MockServer:
    """Faux serveur HTTP qui garde les requêtes reçues (imite Telegram / Google / Claude).
    `reply` : un dictionnaire (réponse 200) ou une fonction (chemin, corps) -> (code, dictionnaire)."""
    def __init__(self, reply):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
                outer.requests.append((self.path, dict(self.headers), body))
                code, payload = reply(self.path, body) if callable(reply) else (200, reply)
                data = json.dumps(payload).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


class ParserTests(unittest.TestCase):
    def test_snort_tcp(self):
        a = parsers.parse_snort(SNORT_LINE)
        self.assertEqual((a["engine"], a["sid"], a["src_ip"], a["src_port"], a["dst_port"], a["action"]),
                         ("snort", 1000001, "10.77.0.2", 33773, 17, "alert"))
        self.assertEqual(a["severity"], 2)

    def test_snort_icmp_has_no_port(self):
        a = parsers.parse_snort(SNORT_ICMP)
        self.assertIsNone(a["src_port"]); self.assertIsNone(a["dst_port"]); self.assertEqual(a["proto"], "ICMP")

    def test_snort_garbage(self):
        self.assertIsNone(parsers.parse_snort("n'importe quoi"))
        self.assertIsNone(parsers.parse_snort(""))

    def test_suricata_blocked(self):
        a = parsers.parse_suricata(EVE_LINE)
        self.assertEqual((a["engine"], a["sid"], a["action"], a["dst_port"]), ("suricata", 1000004, "blocked", 80))
        self.assertEqual(a["ts"], "2026-10-25T17:44:20.576999Z")

    def test_suricata_ignores_other_events_and_garbage(self):
        self.assertIsNone(parsers.parse_suricata('{"event_type":"stats","stats":{}}'))
        self.assertIsNone(parsers.parse_suricata("pas du json"))
        self.assertIsNone(parsers.parse_suricata('{"event_type":"alert"'))   # ligne coupée


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.base = parsers.parse_snort(SNORT_LINE)

    def test_repeated_packets_become_one_incident(self):
        results = [db.insert_alert(self.conn, {**self.base, "ts": f"2026-10-25T10:00:{i:02d}.000000Z"}) for i in range(5)]
        self.assertEqual(results, [True, False, False, False, False])
        row = self.conn.execute("SELECT hits FROM alerts").fetchone()
        self.assertEqual(row["hits"], 5)

    def test_new_incident_after_the_window(self):
        db.insert_alert(self.conn, {**self.base, "ts": "2026-10-25T10:00:00.000000Z"})
        self.assertTrue(db.insert_alert(self.conn, {**self.base, "ts": "2026-10-25T10:05:00.000000Z"}))

    def test_other_source_is_a_separate_incident(self):
        db.insert_alert(self.conn, {**self.base, "ts": "2026-10-25T10:00:00.000000Z"})
        self.assertTrue(db.insert_alert(self.conn, {**self.base, "src_ip": "10.77.0.9", "ts": "2026-10-25T10:00:01.000000Z"}))


class CollectorTests(unittest.TestCase):
    def test_reads_only_complete_lines_and_only_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "alert")
            conn = db.connect(os.path.join(d, "t.db"))
            with open(path, "w") as f:
                f.write(SNORT_LINE + "\n" + SNORT_ICMP)            # 2e ligne pas encore terminée
            self.assertEqual(len(collector.read_new_lines(conn, path)), 1)
            self.assertEqual(collector.read_new_lines(conn, path), [])
            with open(path, "a") as f:
                f.write("\n")
            self.assertEqual(len(collector.read_new_lines(conn, path)), 1)

    def test_restart_after_truncation_rereads_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "alert")
            conn = db.connect(os.path.join(d, "t.db"))
            open(path, "w").write((SNORT_LINE + "\n") * 3)
            collector.read_new_lines(conn, path)
            open(path, "w").write(SNORT_ICMP + "\n")               # fichier vidé puis réécrit (plus court)
            self.assertEqual(len(collector.read_new_lines(conn, path)), 1)


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.server = MockServer({"ok": True})
        self._old = (config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, config.TELEGRAM_API_BASE)
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, config.TELEGRAM_API_BASE = "TOKEN123", "42", self.server.url
        telegram._sent.clear()

    def tearDown(self):
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, config.TELEGRAM_API_BASE = self._old
        self.server.close()

    def test_message_is_sent_with_the_right_content(self):
        alert = parsers.parse_suricata(EVE_LINE)
        analysis = {"summary": "Du SQL <b>dangereux</b>", "advice": "Bloquer l'IP", "level": 5}
        self.assertTrue(telegram.notify(alert, analysis))
        path, _, body = self.server.requests[0]
        self.assertEqual(path, "/botTOKEN123/sendMessage")
        self.assertIn("chat_id=42", body)
        self.assertIn("BLOQU", body.replace("%C3%89", "É"))
        self.assertNotIn("<b>dangereux</b>", body)                   # le HTML venant de l'analyse est échappé

    def test_disabled_without_token(self):
        config.TELEGRAM_BOT_TOKEN = ""
        self.assertFalse(telegram.send("x"))
        self.assertEqual(self.server.requests, [])

    def test_rate_limit(self):
        for _ in range(telegram.MAX_PER_MINUTE + 5):
            telegram.send("x")
        self.assertEqual(len(self.server.requests), telegram.MAX_PER_MINUTE)

    def test_unreachable_server_does_not_crash(self):
        config.TELEGRAM_API_BASE = "http://127.0.0.1:9"
        self.assertFalse(telegram.send("x"))


def gemini_answer(items_ids):
    text = json.dumps([{"id": i, "summary": f"Explication IA {i}.", "advice": "Bloquer.", "level": 3} for i in items_ids])
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def ids_in(body):
    """Les id envoyés à l'IA, relus dans le texte de la requête."""
    prompt = json.loads(body)["contents"][0]["parts"][0]["text"]
    return [a["id"] for a in json.loads(prompt.split("Alertes :\n")[1])]


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        reset_settings()
        self.conn = db.connect(":memory:")
        self.saved = {k: getattr(_config, k) for k in ("GEMINI_API_KEY", "GEMINI_API_BASE", "AI_PROVIDER", "ANTHROPIC_API_KEY")}
        _config.GEMINI_API_KEY, _config.AI_PROVIDER, _config.ANTHROPIC_API_KEY = "k" * 30, "", ""
        self.now = [1000.0]
        self.worker = analyzer.Worker(self.conn, clock=lambda: self.now[0])

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(_config, k, v)

    def add_alerts(self, n, first_sid=1000001):
        for i in range(n):
            db.insert_alert(self.conn, {"ts": "2026-10-25T10:00:00.000000Z", "engine": "suricata", "sid": first_sid + i,
                                        "signature": f"Règle {i}", "category": "c", "severity": 2, "proto": "TCP",
                                        "src_ip": "10.1.1.1", "src_port": 1, "dst_ip": "10.2.2.2", "dst_port": 80, "action": "alert"})

    def server(self, fn):
        srv = MockServer(fn)
        _config.GEMINI_API_BASE = srv.url
        self.addCleanup(srv.close)
        return srv

    # -- lecture de la réponse --
    def test_parse_keeps_only_valid_entries(self):
        text = 'bla [{"id":1,"summary":"a","advice":"b","level":9},{"id":2,"summary":"","advice":"b","level":2},' \
               '{"id":99,"summary":"x","advice":"y","level":1},{"id":3}]'
        out = analyzer.parse_batch(text, {1, 2, 3})
        self.assertEqual(list(out), [1])
        self.assertEqual(out[1]["level"], 5)                       # 9 borné à 5

    def test_parse_rejects_garbage(self):
        with self.assertRaises(analyzer.ProviderError):
            analyzer.parse_batch("pas de json", {1})

    def test_prompt_never_contains_ip_addresses(self):
        self.add_alerts(1)
        prompt = analyzer.build_prompt(self.worker.pending())
        self.assertNotIn("10.1.1.1", prompt)
        self.assertNotIn("10.2.2.2", prompt)

    # -- texte intégré --
    def test_builtin_text_is_instant_and_stored_as_local(self):
        r = analyzer.get_analysis(self.conn, {"sid": 1000004})
        self.assertEqual((r["source"], r["level"]), ("local", 5))
        self.assertEqual(self.conn.execute("SELECT source FROM analyses").fetchone()["source"], "local")

    # -- le lot --
    def test_one_request_explains_everything_and_replaces_builtin_text(self):
        self.add_alerts(3)
        for sid in (1000001, 1000002, 1000003):
            analyzer.get_analysis(self.conn, {"sid": sid})
        srv = self.server(lambda path, body: (200, gemini_answer(ids_in(body))))
        self.assertEqual(self.worker.run_once(), 3)
        self.assertEqual(len(srv.requests), 1)                     # UNE requête pour 3 alertes
        self.assertEqual({r["source"] for r in self.conn.execute("SELECT source FROM analyses")}, {"gemini"})
        self.assertEqual(self.worker.run_once(), 0)                # plus rien à expliquer : aucun nouvel appel
        self.assertEqual(len(srv.requests), 1)

    def test_batches_are_capped_at_batch_size(self):
        self.add_alerts(45)
        srv = self.server(lambda path, body: (200, gemini_answer(ids_in(body))))
        self.worker.run_once()
        self.assertEqual(len(ids_in(srv.requests[0][2])), analyzer.BATCH_SIZE)
        self.assertEqual(self.worker.pending_count(), 25)

    def test_key_is_sent_in_header_not_in_url(self):
        self.add_alerts(1)
        srv = self.server(lambda path, body: (200, gemini_answer(ids_in(body))))
        self.worker.run_once()
        path, headers, _ = srv.requests[0]
        self.assertNotIn("k" * 30, path)
        self.assertEqual({k.lower(): v for k, v in headers.items()}["x-goog-api-key"], "k" * 30)

    # -- limites de débit --
    def test_rate_limited_primary_falls_back_to_second_model(self):
        self.add_alerts(2)

        def reply(path, body):
            if "gemini-3.5-flash-lite" in path:
                return 429, {"error": {"code": 429, "details": [{"@type": "x.RetryInfo", "retryDelay": "30s"}]}}
            return 200, gemini_answer(ids_in(body))
        srv = self.server(reply)
        self.assertEqual(self.worker.run_once(), 2)
        self.assertEqual(len(srv.requests), 2)
        self.assertIn("gemini-3.1-flash-lite", srv.requests[1][0])
        self.now[0] += 5                                           # le modèle principal se repose encore 30 s
        self.add_alerts(1, first_sid=1000100)
        self.worker.run_once()
        self.assertIn("gemini-3.1-flash-lite", srv.requests[2][0])

    def test_all_models_limited_keeps_builtin_text_and_backs_off(self):
        self.add_alerts(1)
        analyzer.get_analysis(self.conn, {"sid": 1000001})
        srv = self.server(lambda path, body: (429, {"error": {"code": 429}}))
        self.assertEqual(self.worker.run_once(), 0)
        self.assertEqual(self.conn.execute("SELECT source FROM analyses").fetchone()["source"], "local")
        count = len(srv.requests)
        self.worker.run_once()                                     # pause : aucun nouvel appel tout de suite
        self.assertEqual(len(srv.requests), count)
        status = json.loads(db.get_state(self.conn, "ai_status"))
        self.assertFalse(status["ok"])
        self.assertIn("Limite", status["error"])

    def test_never_exceeds_requests_per_minute_budget(self):
        self.add_alerts(1)
        srv = self.server(lambda path, body: (500, {"error": {}}))
        for _ in range(40):
            self.worker.wait_until = 0
            self.worker.model_wait.clear()
            self.worker.run_once()
        self.assertLessEqual(len(srv.requests), analyzer.MAX_RPM)

    def test_refused_key_stops_immediately(self):
        self.add_alerts(1)
        srv = self.server(lambda path, body: (400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}))
        self.worker.run_once()
        self.assertEqual(len(srv.requests), 1)                     # pas de modèle de secours avec une mauvaise clé
        self.assertIn("Clé refusée", json.loads(db.get_state(self.conn, "ai_status"))["error"])

    def test_missing_ids_are_retried_later_not_in_a_loop(self):
        self.add_alerts(2)
        srv = self.server(lambda path, body: (200, gemini_answer(ids_in(body)[:1])))   # l'IA « oublie » une alerte
        self.assertEqual(self.worker.run_once(), 1)
        self.assertEqual(self.worker.pending(), [])                # mise en pause (pas de boucle infinie)
        self.now[0] += 200
        self.assertEqual(len(self.worker.pending()), 1)            # réessayée plus tard

    def test_provider_none_makes_no_call(self):
        self.add_alerts(1)
        _config.AI_PROVIDER = "none"
        srv = self.server(lambda path, body: (200, gemini_answer([])))
        self.assertEqual(self.worker.run_once(), 0)
        self.assertEqual(srv.requests, [])

    # -- test d'une clé avant enregistrement --
    def test_test_provider_ok_and_refused(self):
        self.server(lambda path, body: (200, gemini_answer([1])))
        self.assertTrue(analyzer.test_provider("gemini", "k" * 30)["ok"])
        self.server(lambda path, body: (400, {"error": {"message": "API key not valid"}}))
        bad = analyzer.test_provider("gemini", "k" * 30)
        self.assertFalse(bad["ok"])
        self.assertIn("Clé refusée", bad["message"])


@unittest.skipIf(dashboard is None, "Flask n'est pas installé (utilise .venv/bin/python)")
class DashboardStateTests(unittest.TestCase):
    """L'état de chaque attaque : pas encore vue / repérée mais passée / arrêtée."""

    def setUp(self):
        self.conn = db.connect(":memory:")

    def add(self, engine, sid, action, ts):
        db.insert_alert(self.conn, {"ts": ts, "engine": engine, "sid": sid, "signature": "x", "category": "c",
                                    "severity": 2, "proto": "TCP", "src_ip": "1.1.1.1", "src_port": 1,
                                    "dst_ip": "2.2.2.2", "dst_port": 80, "action": action})

    def states(self):
        return {a["key"]: a["state"] for a in dashboard.build_summary(self.conn)["attacks"]}

    def test_nothing_seen_yet(self):
        self.assertEqual(set(self.states().values()), {"waiting"})

    def test_detected_but_not_blocked_is_passed(self):
        self.add("suricata", 1000004, "alert", "2026-10-25T10:00:00.000000Z")
        self.assertEqual(self.states()["sqli"], "passed")
        self.assertEqual(self.states()["scan"], "waiting")

    def test_snort_alone_counts_as_passed(self):
        self.add("snort", 1000003, "alert", "2026-10-25T10:00:00.000000Z")
        self.assertEqual(self.states()["icmp"], "passed")

    def test_blocked_is_stopped_and_latest_wins(self):
        self.add("suricata", 1000001, "alert", "2026-10-25T10:00:00.000000Z")      # d'abord en mode IDS
        self.add("suricata", 1000001, "blocked", "2026-10-25T10:10:00.000000Z")    # puis en mode IPS
        self.assertEqual(self.states()["scan"], "stopped")
        self.add("suricata", 1000001, "alert", "2026-10-25T10:20:00.000000Z")      # retour en mode IDS
        self.assertEqual(self.states()["scan"], "passed")


@unittest.skipIf(dashboard is None, "Flask n'est pas installé (utilise .venv/bin/python)")
class SettingsPageTests(unittest.TestCase):
    """La page Réglages : les secrets ne fuient jamais, et seule la machine locale (ou un code) peut modifier."""
    REMOTE = {"REMOTE_ADDR": "192.168.56.1"}
    KEY = "AIzaSyTESTKEY_0123456789abcdefghijk"
    TOKEN = "123456789:AAH-test_token_0123456789abcdefghij"

    def setUp(self):
        reset_settings()
        self.db_path = os.path.join(_TMP, "t.db")
        self.saved = {k: getattr(_config, k) for k in ("DB_PATH", "GEMINI_API_BASE", "TELEGRAM_API_BASE", "GEMINI_API_KEY",
                                                        "AI_PROVIDER", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
        _config.DB_PATH = self.db_path
        _config.GEMINI_API_KEY = _config.AI_PROVIDER = _config.TELEGRAM_BOT_TOKEN = _config.TELEGRAM_CHAT_ID = ""
        self.client = dashboard.app.test_client()
        dashboard._pin_fail.update(count=0, until=0.0)
        telegram._sent.clear()
        self.google = MockServer(lambda path, body: (200, gemini_answer([1])))
        self.tg = MockServer(self.telegram_reply)
        _config.GEMINI_API_BASE, _config.TELEGRAM_API_BASE = self.google.url, self.tg.url
        self.chats = [{"message": {"chat": {"id": 42, "first_name": "Awa"}}}]

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(_config, k, v)
        self.google.close(); self.tg.close()
        reset_settings()

    def telegram_reply(self, path, body):
        if "getMe" in path:
            return 200, {"ok": True, "result": {"username": "harden_bot"}}
        if "getUpdates" in path:
            return 200, {"ok": True, "result": self.chats}
        return 200, {"ok": True, "result": {}}

    def post(self, url, payload, remote=False, headers=None):
        return self.client.post(url, json=payload, headers=headers or {}, environ_base=self.REMOTE if remote else {})

    def test_secrets_are_never_returned(self):
        self.assertTrue(self.post("/api/settings/ai", {"provider": "gemini", "key": self.KEY}).get_json()["ok"])
        self.assertTrue(self.post("/api/settings/telegram/token", {"token": self.TOKEN}).get_json()["ok"])
        raw = self.client.get("/api/settings").get_data(as_text=True)
        self.assertNotIn(self.KEY, raw)
        self.assertNotIn(self.TOKEN, raw)
        view = json.loads(raw)
        self.assertTrue(view["ai"]["key_set"])
        self.assertEqual(view["ai"]["key_hint"], "…" + self.KEY[-4:])
        self.assertEqual(view["telegram"]["bot"], "harden_bot")

    def test_key_is_tested_before_being_saved(self):
        self.google.close()
        self.google = MockServer(lambda path, body: (400, {"error": {"message": "API key not valid"}}))
        _config.GEMINI_API_BASE = self.google.url
        r = self.post("/api/settings/ai", {"provider": "gemini", "key": self.KEY}).get_json()
        self.assertFalse(r["ok"])
        self.assertIn("Clé refusée", r["message"])
        self.assertFalse(_config.SETTINGS_FILE.exists())           # une clé qui ne marche pas n'est pas enregistrée

    def test_saved_settings_override_env_and_file_is_private(self):
        _config.GEMINI_MODEL = "autre-modele"
        self.post("/api/settings/ai", {"provider": "gemini", "key": self.KEY})
        self.assertEqual(_config.setting("GEMINI_API_KEY"), self.KEY)
        self.assertEqual(oct(_config.SETTINGS_FILE.stat().st_mode & 0o777), "0o600")
        _config.GEMINI_MODEL = "gemini-3.5-flash-lite"

    def test_pasted_key_with_spaces_and_quotes_is_cleaned(self):
        r = self.post("/api/settings/ai", {"provider": "gemini", "key": f'  "{self.KEY[:10]} {self.KEY[10:]}"\n'}).get_json()
        self.assertTrue(r["ok"])
        self.assertEqual(_config.setting("GEMINI_API_KEY"), self.KEY)

    def test_remote_client_needs_the_pin(self):
        r = self.post("/api/settings/ai", {"provider": "gemini", "key": self.KEY}, remote=True)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(_config.SETTINGS_FILE.exists())
        r = self.post("/api/settings/ai", {"provider": "gemini", "key": self.KEY}, remote=True,
                      headers={"X-Admin-Pin": dashboard.ADMIN_PIN})
        self.assertTrue(r.get_json()["ok"])

    def test_wrong_pin_is_locked_after_five_tries(self):
        for _ in range(5):
            self.post("/api/settings/ai", {"provider": "none"}, remote=True, headers={"X-Admin-Pin": "000000"})
        r = self.post("/api/settings/ai", {"provider": "none"}, remote=True, headers={"X-Admin-Pin": dashboard.ADMIN_PIN})
        self.assertEqual(r.status_code, 429)

    def test_view_tells_remote_clients_they_cannot_edit(self):
        view = self.client.get("/api/settings", environ_base=self.REMOTE).get_json()
        self.assertEqual((view["can_edit"], view["needs_pin"]), (False, True))
        view = self.client.get("/api/settings").get_json()
        self.assertEqual((view["can_edit"], view["needs_pin"]), (True, False))

    def test_cross_site_and_non_json_requests_are_refused(self):
        r = self.post("/api/settings/ai", {"provider": "none"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/settings/ai", data="provider=none", content_type="application/x-www-form-urlencoded")
        self.assertEqual(r.status_code, 400)

    def test_telegram_three_steps(self):
        bad = self.post("/api/settings/telegram/token", {"token": "pas-un-token"}).get_json()
        self.assertFalse(bad["ok"])
        self.assertEqual(self.tg.requests, [])                      # format invalide : on n'appelle même pas Telegram
        self.assertTrue(self.post("/api/settings/telegram/token", {"token": self.TOKEN}).get_json()["ok"])
        self.chats = []
        self.assertFalse(self.post("/api/settings/telegram/chat", {}).get_json()["ok"])     # pas encore de /start
        self.chats = [{"message": {"chat": {"id": 42, "first_name": "Awa"}}}]
        found = self.post("/api/settings/telegram/chat", {}).get_json()
        self.assertEqual((found["ok"], found["name"]), (True, "Awa"))
        self.assertTrue(self.post("/api/settings/telegram/test", {}).get_json()["ok"])
        self.assertIn("/sendMessage", self.tg.requests[-1][0])
        self.assertIn("chat_id=42", self.tg.requests[-1][2])

    def test_several_chats_ask_the_user_to_choose(self):
        self.post("/api/settings/telegram/token", {"token": self.TOKEN})
        self.chats = [{"message": {"chat": {"id": 1, "first_name": "A"}}}, {"message": {"chat": {"id": 2, "first_name": "B"}}}]
        r = self.post("/api/settings/telegram/chat", {}).get_json()
        self.assertEqual([c["id"] for c in r["choose"]], [1, 2])
        self.assertEqual(self.post("/api/settings/telegram/chat", {"chat_id": 2}).get_json()["name"], "B")

    def test_changing_the_bot_forgets_the_old_chat(self):
        self.post("/api/settings/telegram/token", {"token": self.TOKEN})
        self.post("/api/settings/telegram/chat", {})
        self.post("/api/settings/telegram/token", {"token": "987654321:" + "B" * 35})
        self.assertFalse(self.client.get("/api/settings").get_json()["telegram"]["chat_set"])

    def test_telegram_test_refused_until_configured(self):
        self.assertEqual(self.post("/api/settings/telegram/test", {}).status_code, 400)

    def test_clear_buttons(self):
        self.post("/api/settings/ai", {"provider": "gemini", "key": self.KEY})
        self.post("/api/settings/ai/clear", {"provider": "gemini"})
        self.assertFalse(self.client.get("/api/settings").get_json()["ai"]["key_set"])


class FakeProc:
    def __init__(self, code=0):
        self.code = code
        self.release = threading.Event()

    def wait(self):
        self.release.wait(5)
        return self.code


class LabDaemonTests(unittest.TestCase):
    """Le chef d'orchestre : liste fermée de commandes, jamais de texte libre, jamais deux actions en même temps."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = {k: getattr(labd, k) for k in ("MODE_FILE", "DEMO_LOG", "STATE_DIR")}
        labd.MODE_FILE = os.path.join(self.dir, "mode")
        labd.DEMO_LOG = os.path.join(self.dir, "demo.log")
        labd.STATE_DIR = self.dir
        os.environ["LAB_SETTLE"] = "0"
        self.calls, self.procs = [], []

        def fake_run(cmd, **kw):
            self.calls.append(cmd)
            with open(labd.MODE_FILE, "w") as f:
                f.write(cmd[-1])
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        def fake_popen(cmd, **kw):
            self.calls.append(cmd)
            proc = FakeProc()
            self.procs.append(proc)
            return proc
        self.lab = labd.Lab(popen=fake_popen, run=fake_run)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(labd, k, v)
        os.environ.pop("LAB_SETTLE", None)

    def wait_idle(self):
        for _ in range(100):
            if not self.lab.busy:
                return
            time.sleep(0.02)
        self.fail("le changement de mode ne se termine pas")

    def test_unknown_commands_are_refused(self):
        for bad in (None, "x", {"cmd": "rm"}, {"cmd": "mode", "value": "ids; reboot"}, {"cmd": "demo", "scenario": "../etc"}):
            self.assertFalse(self.lab.handle(bad)["ok"])
        self.assertEqual(self.calls, [])

    def test_mode_change_runs_lab_script_and_remembers(self):
        self.assertTrue(self.lab.handle({"cmd": "mode", "value": "ips"})["ok"])
        self.wait_idle()
        self.assertTrue(self.calls[0][0].endswith("scripts/lab.sh"))
        self.assertEqual(self.calls[0][1], "ips")
        self.assertEqual(self.lab.status()["mode"], "ips")
        self.assertEqual(open(os.path.join(self.dir, "mode")).read(), "ips")

    def test_demo_needs_probes_and_runs_attacker_in_namespace(self):
        self.assertFalse(self.lab.handle({"cmd": "demo"})["ok"])          # aucun mode choisi : sondes arrêtées
        self.lab.handle({"cmd": "mode", "value": "ids"}); self.wait_idle()
        self.assertTrue(self.lab.handle({"cmd": "demo", "scenario": "all"})["ok"])
        cmd = self.calls[-1]
        self.assertEqual(cmd[:4], ["ip", "netns", "exec", "hdlab"])
        self.assertIn("runuser", cmd)
        self.assertEqual(cmd[-2:-1], ["all"])

    def test_one_action_at_a_time(self):
        self.lab.handle({"cmd": "mode", "value": "ids"}); self.wait_idle()
        self.assertTrue(self.lab.handle({"cmd": "demo"})["ok"])
        self.assertFalse(self.lab.handle({"cmd": "demo"})["ok"])                       # déjà en cours
        self.assertFalse(self.lab.handle({"cmd": "mode", "value": "ips"})["ok"])       # pas pendant une démo
        self.procs[0].release.set()
        for _ in range(100):
            if not self.lab.demo["running"]:
                break
            time.sleep(0.02)
        self.assertFalse(self.lab.demo["running"])
        self.assertEqual(self.lab.demo["code"], 0)

    def test_progress_is_read_from_the_log_without_colours(self):
        with open(labd.DEMO_LOG, "w") as f:
            f.write("\x1b[1m[0/4] Contrôle\x1b[0m\n   → OK\n\x1b[1m[1/4] Scan de ports\x1b[0m\n[2/4] Bruteforce SSH\n")
        lines, step = self.lab.demo_lines()
        self.assertEqual(step, 2)
        self.assertNotIn("\x1b", "".join(lines))

    def test_failed_mode_change_reports_error(self):
        self.lab.run = lambda cmd, **kw: type("R", (), {"returncode": 1, "stdout": "", "stderr": "boum\nsnort introuvable"})()
        self.lab.handle({"cmd": "mode", "value": "ids"}); self.wait_idle()
        self.assertEqual(self.lab.status()["error"], "snort introuvable")

    def test_socket_roundtrip_and_missing_socket(self):
        path = os.path.join(self.dir, "lab.sock")
        server = labd.make_server(self.lab, path=path)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            self.assertTrue(labctl.call({"cmd": "status"}, path=path)["available"])
            self.assertFalse(labctl.call({"cmd": "nope"}, path=path)["ok"])
        finally:
            server.shutdown(); server.server_close()
        self.assertEqual(labctl.call({"cmd": "status"}, path=os.path.join(self.dir, "absent.sock")), {"ok": False, "available": False})


@unittest.skipIf(dashboard is None, "Flask n'est pas installé (utilise .venv/bin/python)")
class DashboardLabTests(unittest.TestCase):
    """Les boutons du dashboard : réservés à cette machine (ou au code), et inertes si le laboratoire n'est pas installé."""
    REMOTE = {"REMOTE_ADDR": "10.88.0.2"}

    def setUp(self):
        self.client = dashboard.app.test_client()
        dashboard._pin_fail.update(count=0, until=0.0)
        self.sent = []
        self.real_call = labctl.call
        labctl.call = lambda req, **kw: (self.sent.append(req), {"ok": True, "available": True, "message": "ok"})[1]

    def tearDown(self):
        labctl.call = self.real_call
        config.TRUSTED_ADDRS = ()

    def post(self, path, body, **kw):
        return self.client.post(path, json=body, **kw)

    def test_local_can_switch_and_start(self):
        self.assertEqual(self.post("/api/lab/mode", {"mode": "ips"}).status_code, 200)
        self.assertEqual(self.post("/api/lab/demo", {"scenario": "all"}).status_code, 200)
        self.assertEqual(self.sent, [{"cmd": "mode", "value": "ips"}, {"cmd": "demo", "scenario": "all"}])

    def test_the_isolated_attacker_cannot_control_the_lab(self):
        self.assertEqual(self.post("/api/lab/mode", {"mode": "ids"}, environ_overrides=self.REMOTE).status_code, 403)
        self.assertEqual(self.post("/api/lab/demo", {}, environ_overrides=self.REMOTE).status_code, 403)
        self.assertEqual(self.post("/api/lab/mode", {"mode": "ids"}, environ_overrides=self.REMOTE, headers={"X-Admin-Pin": "000000"}).status_code, 403)
        self.assertEqual(self.sent, [])

    def test_remote_with_pin_is_allowed(self):
        r = self.post("/api/lab/mode", {"mode": "ids"}, environ_overrides=self.REMOTE, headers={"X-Admin-Pin": dashboard.ADMIN_PIN})
        self.assertEqual(r.status_code, 200)

    def test_trusted_address_counts_as_this_machine(self):
        config.TRUSTED_ADDRS = ("10.0.2.2",)
        self.assertEqual(self.post("/api/lab/mode", {"mode": "ids"}, environ_overrides={"REMOTE_ADDR": "10.0.2.2"}).status_code, 200)
        self.assertEqual(self.post("/api/lab/mode", {"mode": "ids"}, environ_overrides=self.REMOTE).status_code, 403)

    def test_foreign_origin_is_refused(self):
        self.assertEqual(self.post("/api/lab/mode", {"mode": "ids"}, headers={"Origin": "http://evil.example"}).status_code, 403)

    def test_lab_not_installed_is_reported_not_crashed(self):
        labctl.call = lambda req, **kw: {"ok": False, "available": False}
        self.assertFalse(self.client.get("/api/lab").get_json()["available"])
        self.assertEqual(self.post("/api/lab/demo", {}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
