#!/usr/bin/env bash
# Pilote le labo.   sudo ./scripts/lab.sh {ids|ips|stop|status}
#   ids  : Snort alerte + Suricata alerte          (rien n'est bloqué)
#   ips  : Snort alerte + Suricata BLOQUE (drop)   (c'est la comparaison)
set -euo pipefail
[ "$EUID" -eq 0 ] || { echo "Lance avec sudo."; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IFACE="$(cat "$REPO_DIR/.iface" 2>/dev/null || ip route show default | awk '{print $5; exit}')"
RUN=/run/harden; mkdir -p "$RUN" /var/log/snort /var/log/suricata

stop_all() {
  for p in snort suricata; do
    [ -f "$RUN/$p.pid" ] && kill "$(cat "$RUN/$p.pid")" 2>/dev/null || true
    rm -f "$RUN/$p.pid"
  done
  pkill -x snort 2>/dev/null || true
  pkill -x suricata 2>/dev/null || true
  iptables -D INPUT  -j NFQUEUE --queue-num 0 --queue-bypass 2>/dev/null || true
  iptables -D OUTPUT -j NFQUEUE --queue-num 0 --queue-bypass 2>/dev/null || true
}

start_snort() {
  snort -D -q -A fast -c /etc/snort/snort.conf -i "$IFACE" -l /var/log/snort
  sleep 1; pgrep -x snort | head -1 > "$RUN/snort.pid" || true
}

case "${1:-}" in
  ids)
    stop_all; start_snort
    suricata -D -c /etc/suricata/suricata.yaml -i "$IFACE" --pidfile "$RUN/suricata.pid"
    echo "[+] Mode IDS : Snort et Suricata observent et alertent, rien n'est bloqué." ;;
  ips)
    stop_all; start_snort
    # Tout le trafic passe par Suricata avant d'atteindre Ubuntu. --queue-bypass = si Suricata
    # plante, le trafic continue (on ne se coupe pas soi-même du réseau).
    iptables -I INPUT  -j NFQUEUE --queue-num 0 --queue-bypass
    iptables -I OUTPUT -j NFQUEUE --queue-num 0 --queue-bypass
    suricata -D -c /etc/suricata/suricata.yaml -q 0 --pidfile "$RUN/suricata.pid"
    echo "[+] Mode IPS : Suricata BLOQUE les attaques (drop). Snort reste en simple alerte." ;;
  stop)
    stop_all; echo "[+] Tout est arrêté, pare-feu remis à l'état normal." ;;
  status)
    echo "Interface : $IFACE"
    pgrep -x snort    >/dev/null && echo "Snort    : actif" || echo "Snort    : arrêté"
    pgrep -x suricata >/dev/null && echo "Suricata : actif" || echo "Suricata : arrêté"
    iptables -S INPUT | grep -q NFQUEUE && echo "Mode     : IPS (NFQUEUE)" || echo "Mode     : IDS / arrêté" ;;
  *) echo "Usage : sudo $0 {ids|ips|stop|status}"; exit 1 ;;
esac
