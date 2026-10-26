#!/usr/bin/env bash
# Réseau interne du « mode une machine » : un attaquant isolé (espace réseau « hdlab ») relié à la machine par un câble virtuel.
#   hd0  = côté machine (10.88.0.1)   |   eth0 dans hdlab = côté attaquant (10.88.0.2)
#   sudo ./scripts/lab-net.sh {up|down|status}
set -euo pipefail
[ "$EUID" -eq 0 ] || { echo "Lance avec sudo."; exit 1; }
NS=hdlab; HOST_IP=10.88.0.1; ATTACKER_IP=10.88.0.2

case "${1:-}" in
  up)
    if ip link show hd0 >/dev/null 2>&1 && ip netns list | grep -q "^$NS"; then echo "réseau déjà prêt"; exit 0; fi
    ip link del hd0 2>/dev/null || true; ip netns del "$NS" 2>/dev/null || true
    ip netns add "$NS"
    ip link add hd0 type veth peer name hdpeer
    ip link set hdpeer netns "$NS"
    ip netns exec "$NS" ip link set hdpeer name eth0
    ip addr add "$HOST_IP/24" dev hd0 && ip link set hd0 up
    ip netns exec "$NS" ip addr add "$ATTACKER_IP/24" dev eth0
    ip netns exec "$NS" ip link set eth0 up
    ip netns exec "$NS" ip link set lo up
    echo "réseau prêt : $HOST_IP (machine) <-> $ATTACKER_IP (attaquant isolé)" ;;
  down)
    ip netns del "$NS" 2>/dev/null || true; ip link del hd0 2>/dev/null || true; echo "réseau supprimé" ;;
  status)
    ip link show hd0 >/dev/null 2>&1 && ip netns list | grep -q "^$NS" && echo "up" || { echo "down"; exit 1; } ;;
  *) echo "Usage : $0 {up|down|status}"; exit 1 ;;
esac
