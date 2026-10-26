"""Le « chef d'orchestre » du mode une machine (il tourne en root, le dashboard non).

Le dashboard ne peut pas changer de mode ni lancer d'attaque : il n'a pas les droits. Il envoie donc des ORDRES à ce programme,
par une porte réservée (un socket Unix accessible au seul groupe « harden »). Ce programme n'accepte qu'une liste fermée :

    status                         l'état du laboratoire
    mode  ids|ips                  passer en Surveillance ou en Protection
    demo  all|scan|ssh|icmp|sqli   lancer les attaques depuis l'attaquant isolé

Jamais de texte libre exécuté, jamais de commande venue du réseau.
"""
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time

REPO = os.environ.get("HARDEN_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOCKET = os.environ.get("LAB_SOCKET", "/run/harden/lab.sock")
STATE_DIR = os.environ.get("LAB_STATE", "/var/lib/harden-defense")
MODE_FILE = os.environ.get("MODE_FILE", "/run/harden/mode")
DEMO_LOG = os.environ.get("DEMO_LOG", "/run/harden/demo.log")
TARGET = os.environ.get("LAB_TARGET", "10.88.0.1")
NAMESPACE = os.environ.get("LAB_NAMESPACE", "hdlab")
DASHBOARD = os.environ.get("LAB_DASHBOARD", f"http://{TARGET}:5000")
ATTACKER_USER = os.environ.get("LAB_ATTACKER", "harden-attacker")
MODES = ("ids", "ips")
SCENARIOS = ("all", "scan", "ssh", "icmp", "sqli")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
STEP = re.compile(r"^\[(\d)/4\]")


class Lab:
    """L'état du laboratoire et les deux actions possibles. `popen` est remplaçable pour les tests."""

    def __init__(self, popen=subprocess.Popen, run=subprocess.run, clock=time.time):
        self.popen, self.run, self.clock = popen, run, clock
        self.lock = threading.Lock()
        self.busy = None                 # "mode" pendant un changement de mode
        self.error = None
        self.demo = {"running": False, "scenario": None, "started": None, "finished": None, "code": None}
        self.last_mode_change = 0.0

    # ---- lecture ----
    def current_mode(self):
        try:
            with open(MODE_FILE, encoding="utf-8") as f:
                value = f.read().strip()
            return value if value in MODES + ("stopped",) else "unknown"
        except OSError:
            return "unknown"

    def demo_lines(self, n=14):
        try:
            with open(DEMO_LOG, encoding="utf-8", errors="replace") as f:
                lines = [ANSI.sub("", l.rstrip("\n")) for l in f.read().splitlines() if l.strip()]
        except OSError:
            return [], 0
        step = 0
        for l in lines:
            m = STEP.match(l)
            if m:
                step = max(step, int(m.group(1)))
        return lines[-n:], step

    def status(self):
        lines, step = self.demo_lines()
        return {"ok": True, "available": True, "mode": self.current_mode(), "busy": self.busy, "error": self.error,
                "demo": {**self.demo, "step": step, "total": 4, "lines": lines}}

    # ---- actions ----
    def set_mode(self, value):
        if value not in MODES:
            return {"ok": False, "message": "Mode inconnu."}
        with self.lock:
            if self.busy:
                return {"ok": False, "message": "Un changement de mode est déjà en cours."}
            if self.demo["running"]:
                return {"ok": False, "message": "Attends la fin de la démonstration."}
            self.busy, self.error = "mode", None
        threading.Thread(target=self._apply_mode, args=(value,), daemon=True).start()
        return {"ok": True, "message": "Changement de mode en cours (une dizaine de secondes)."}

    def _apply_mode(self, value):
        try:
            res = self.run([os.path.join(REPO, "scripts", "lab.sh"), value], capture_output=True, text=True, timeout=120,
                           env={**os.environ, "HD_IFACE": "hd0"})
            if res.returncode != 0:
                self.error = (res.stderr or res.stdout or "échec").strip().splitlines()[-1][:200]
            else:
                os.makedirs(STATE_DIR, exist_ok=True)
                with open(os.path.join(STATE_DIR, "mode"), "w", encoding="utf-8") as f:
                    f.write(value)
                time.sleep(float(os.environ.get("LAB_SETTLE", "10")))    # le temps que les sondes démarrent vraiment
        except Exception as exc:                                         # ne jamais faire tomber le programme
            self.error = str(exc)[:200]
        finally:
            self.busy = None

    def run_demo(self, scenario):
        if scenario not in SCENARIOS:
            return {"ok": False, "message": "Scénario inconnu."}
        with self.lock:
            if self.busy:
                return {"ok": False, "message": "Les sondes démarrent : réessaie dans quelques secondes."}
            if self.demo["running"]:
                return {"ok": False, "message": "Une démonstration est déjà en cours."}
            if self.current_mode() not in MODES:
                return {"ok": False, "message": "Les sondes ne tournent pas. Choisis d'abord un mode."}
            self.demo = {"running": True, "scenario": scenario, "started": self.clock(), "finished": None, "code": None}
        cmd = ["ip", "netns", "exec", NAMESPACE, "runuser", "-u", ATTACKER_USER, "--",
               os.path.join(REPO, "kali", "attack.sh"), TARGET, scenario, DASHBOARD]
        try:
            os.makedirs(os.path.dirname(DEMO_LOG), exist_ok=True)
            log = open(DEMO_LOG, "w", encoding="utf-8")
            os.chmod(DEMO_LOG, 0o644)
            proc = self.popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except Exception as exc:
            self.demo.update(running=False, finished=self.clock(), code=-1)
            return {"ok": False, "message": f"Impossible de lancer les attaques : {exc}"}
        threading.Thread(target=self._wait_demo, args=(proc, log), daemon=True).start()
        return {"ok": True, "message": "Démonstration lancée."}

    def _wait_demo(self, proc, log):
        code = proc.wait()
        log.close()
        self.demo.update(running=False, finished=self.clock(), code=code)

    # ---- point d'entrée des ordres ----
    def handle(self, request):
        cmd = request.get("cmd") if isinstance(request, dict) else None
        if cmd == "status":
            return self.status()
        if cmd == "mode":
            return self.set_mode(request.get("value"))
        if cmd == "demo":
            return self.run_demo(request.get("scenario", "all"))
        return {"ok": False, "message": "Commande inconnue."}


def make_server(lab, path=SOCKET, group="harden"):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                request = json.loads(self.rfile.readline(4096).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                request = None
            try:
                reply = lab.handle(request)
            except Exception as exc:
                reply = {"ok": False, "message": f"erreur interne : {exc}"}
            self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    server = Server(path, Handler)
    os.chmod(path, 0o660)
    try:
        import grp
        os.chown(path, 0, grp.getgrnam(group).gr_gid)
    except (KeyError, ImportError, PermissionError):
        os.chmod(path, 0o666 if os.environ.get("LAB_OPEN_SOCKET") else 0o660)
    return server


def boot(lab):
    """Au démarrage : réseau interne, puis le dernier mode choisi (Surveillance par défaut)."""
    subprocess.run([os.path.join(REPO, "scripts", "lab-net.sh"), "up"], check=False)
    try:
        with open(os.path.join(STATE_DIR, "mode"), encoding="utf-8") as f:
            mode = f.read().strip()
    except OSError:
        mode = "ids"
    lab.set_mode(mode if mode in MODES else "ids")


def main():
    lab = Lab()
    server = make_server(lab)
    print(f"[labd] à l'écoute sur {SOCKET}", flush=True)
    threading.Thread(target=boot, args=(lab,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
