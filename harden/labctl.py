"""Le « télécommande » du laboratoire : parle au chef d'orchestre (labd) par son socket.

Utilisée par le dashboard (boutons) et par la commande `harden` (terminal) :
    python -m harden.labctl status | ids | ips | demo [scénario]
"""
import json
import os
import socket
import sys

SOCKET = os.environ.get("LAB_SOCKET", "/run/harden/lab.sock")


def call(request, timeout=3.0, path=None):
    """Envoie un ordre. Retourne toujours un dictionnaire ; {'available': False} si le laboratoire n'est pas installé."""
    path = path or SOCKET
    if not os.path.exists(path):
        return {"ok": False, "available": False}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(path)
            s.sendall((json.dumps(request) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        return json.loads(data.decode("utf-8"))
    except PermissionError:
        return {"ok": False, "available": False, "message": "Accès refusé au laboratoire."}
    except (OSError, ValueError):
        return {"ok": False, "available": False}


MODE_LABEL = {"ids": "Surveillance (IDS)", "ips": "Protection (IPS)", "stopped": "arrêté", "unknown": "inconnu"}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in ("ids", "ips"):
        r = call({"cmd": "mode", "value": cmd})
    elif cmd == "demo":
        r = call({"cmd": "demo", "scenario": sys.argv[2] if len(sys.argv) > 2 else "all"})
    elif cmd == "status":
        r = call({"cmd": "status"})
        if r.get("available") is not False:
            d = r["demo"]
            print(f"Mode : {MODE_LABEL.get(r['mode'], r['mode'])}" + ("   (changement en cours…)" if r.get("busy") else ""))
            print("Démonstration : " + ("en cours (étape %d/4)" % d["step"] if d["running"] else "aucune en cours"))
            return 0
    else:
        print("Usage : harden {status|ids|ips|demo}")
        return 2
    if r.get("available") is False:
        print(r.get("message") or "Le laboratoire n'est pas démarré (essaie : sudo systemctl start harden-lab).")
        return 1
    print(r.get("message", "ok"))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
