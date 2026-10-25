"""Tests automatiques :  python3 -m unittest discover -s tests -v   (aucune dépendance, aucun réseau réel)"""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harden import analyzer, collector, config, db, parsers, telegram  # noqa: E402

SNORT_LINE = ("10/25-17:40:59.002045  [**] [1:1000001:1] HD Scan de ports SYN [**] "
              "[Classification: Attempted Information Leak] [Priority: 2] {TCP} 10.77.0.2:33773 -> 10.77.0.1:17")
SNORT_ICMP = ("10/25-17:41:00.100000  [**] [1:1000003:1] HD Flood ICMP [**] "
              "[Classification: Attempted Denial of Service] [Priority: 2] {ICMP} 10.77.0.2 -> 10.77.0.1")
EVE_LINE = json.dumps({
    "timestamp": "2026-10-25T17:44:20.576999+0000", "event_type": "alert", "src_ip": "10.77.0.2", "src_port": 51424,
    "dest_ip": "10.77.0.1", "dest_port": 80, "proto": "TCP",
    "alert": {"action": "blocked", "signature_id": 1000004, "signature": "HD Injection SQL (UNION SELECT)",
              "category": "Web Application Attack", "severity": 1}})


class MockServer:
    """Faux serveur HTTP qui garde les requêtes reçues (imite Telegram / l'API de Claude)."""
    def __init__(self, reply):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
                outer.requests.append((self.path, dict(self.headers), body))
                data = json.dumps(reply).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
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


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.alert = parsers.parse_suricata(EVE_LINE)
        self._old = (config.ANTHROPIC_API_KEY, config.ANTHROPIC_API_BASE)

    def tearDown(self):
        config.ANTHROPIC_API_KEY, config.ANTHROPIC_API_BASE = self._old

    def test_local_fallback_without_key(self):
        config.ANTHROPIC_API_KEY = ""
        r = analyzer.get_analysis(self.conn, self.alert)
        self.assertEqual((r["source"], r["level"]), ("local", 5))

    def test_claude_answer_is_used_and_cached(self):
        reply = {"content": [{"type": "text", "text": 'Voici : {"summary": "Injection SQL.", "advice": "Bloquer.", "level": 9}'}]}
        server = MockServer(reply)
        try:
            config.ANTHROPIC_API_KEY, config.ANTHROPIC_API_BASE = "sk-test", server.url
            r = analyzer.get_analysis(self.conn, self.alert)
            self.assertEqual((r["source"], r["summary"], r["level"]), ("claude", "Injection SQL.", 5))   # 9 borné à 5
            headers = {k.lower(): v for k, v in server.requests[0][1].items()}
            self.assertEqual(headers.get("x-api-key"), "sk-test")
            analyzer.get_analysis(self.conn, self.alert)
            self.assertEqual(len(server.requests), 1)                # 2e fois : lu en base, pas de nouvel appel payant
        finally:
            server.close()

    def test_api_failure_falls_back_and_retries_later(self):
        config.ANTHROPIC_API_KEY, config.ANTHROPIC_API_BASE = "sk-test", "http://127.0.0.1:9"
        r = analyzer.get_analysis(self.conn, self.alert)
        self.assertEqual(r["source"], "local")
        self.assertIsNone(self.conn.execute("SELECT 1 FROM analyses").fetchone())   # pas mis en cache : on réessaiera


if __name__ == "__main__":
    unittest.main()
