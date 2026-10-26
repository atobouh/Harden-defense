#!/usr/bin/env bash
# Démarre / arrête les 3 services SANS systemd (utile dans un conteneur ou pour tester).  sudo ./scripts/services.sh {start|stop|status}
# Sur une vraie Ubuntu, c'est systemd qui s'en occupe (install.sh l'active) : tu n'as pas besoin de ce script.
set -euo pipefail
[ "$EUID" -eq 0 ] || { echo "Lance avec sudo."; exit 1; }
PREFIX="${HD_PREFIX:-$(cd "$(dirname "$0")/.." && pwd)}"
STATE=/var/lib/harden-defense; LOGS=/var/log/harden; RUN=/run/harden
mkdir -p "$LOGS" "$RUN" "$STATE"; chmod 755 "$RUN"

[ -f /etc/default/harden-defense ] && { set -a; . /etc/default/harden-defense; set +a; }
export HARDEN_HOME="$PREFIX" LAB_STATE="$STATE" PYTHONDONTWRITEBYTECODE=1 FLASK_SKIP_DOTENV=1
export DB_PATH="$STATE/harden.db" SETTINGS_FILE="$STATE/settings.json" PIN_FILE="$STATE/pin"

alive() { [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }
launch() {   # launch NOM [commande...]  (en tant que root si NOM=labd, sinon en tant que « harden »)
  local name="$1"; shift
  alive "$name" && return 0
  if [ "$name" = labd ]; then
    nohup "$@" >>"$LOGS/$name.log" 2>&1 </dev/null & echo $! > "$RUN/$name.pid"
  else
    nohup runuser -u harden -- "$@" >>"$LOGS/$name.log" 2>&1 </dev/null & echo $! > "$RUN/$name.pid"
  fi
}
halt() {
  for n in dashboard collector labd; do
    alive "$n" && kill "$(cat "$RUN/$n.pid")" 2>/dev/null || true
    rm -f "$RUN/$n.pid"
  done
  [ -S "$RUN/lab.sock" ] && rm -f "$RUN/lab.sock"
  "$PREFIX/scripts/lab.sh" stop >/dev/null 2>&1 || true
}

case "${1:-}" in
  start)
    cd "$PREFIX"
    "$PREFIX/scripts/lab-net.sh" up >/dev/null
    chown harden:harden "$STATE"
    launch labd /usr/bin/python3 -m harden.labd
    launch collector "$PREFIX/.venv/bin/python" -m harden.collector
    launch dashboard "$PREFIX/.venv/bin/python" -m harden.dashboard
    echo "[+] Services démarrés (journaux : $LOGS)" ;;
  stop)   halt; echo "[+] Services arrêtés" ;;
  status) for n in labd collector dashboard; do alive "$n" && echo "$n : actif" || echo "$n : arrêté"; done ;;
  *) echo "Usage : sudo $0 {start|stop|status}"; exit 1 ;;
esac
