#!/usr/bin/env bash
# À lancer UNE FOIS sur la VM Ubuntu (défenseur) :  sudo ./scripts/install_defender.sh [interface]
set -euo pipefail

[ "$EUID" -eq 0 ] || { echo "Lance ce script avec sudo."; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IFACE="${1:-$(ip route show default | awk '{print $5; exit}')}"
[ -n "$IFACE" ] || { echo "Interface réseau introuvable. Précise-la : sudo $0 enp0s8"; exit 1; }

IP_CIDR="$(ip -4 -o addr show "$IFACE" | awk '{print $4; exit}')"
HOME_NET="$(python3 -c "import ipaddress,sys; print(ipaddress.ip_interface(sys.argv[1]).network)" "$IP_CIDR")"
echo "[*] Interface : $IFACE   Réseau protégé (HOME_NET) : $HOME_NET"

echo "[*] Installation de Snort et Suricata..."
echo "snort snort/interface string $IFACE"        | debconf-set-selections
echo "snort snort/address_range string $HOME_NET" | debconf-set-selections
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y snort suricata iptables python3 python3-pip

# On lance nous-mêmes les moteurs (voir scripts/lab.sh) : on coupe les services auto
systemctl disable --now snort suricata 2>/dev/null || true

echo "[*] Configuration de Snort (IDS)..."
install -m 644 "$REPO_DIR/config/snort/local.rules" /etc/snort/rules/local.rules
grep -q 'include $RULE_PATH/local.rules' /etc/snort/snort.conf \
  || echo 'include $RULE_PATH/local.rules' >> /etc/snort/snort.conf

echo "[*] Configuration de Suricata (IPS)..."
install -d /var/lib/suricata/rules
install -m 644 "$REPO_DIR/config/suricata/local.rules" /var/lib/suricata/rules/local.rules
grep -q -- '- local.rules' /etc/suricata/suricata.yaml \
  || sed -i '/^rule-files:/a\  - local.rules' /etc/suricata/suricata.yaml
sed -i "s|^\( *HOME_NET:\).*|\1 \"[$HOME_NET]\"|" /etc/suricata/suricata.yaml

echo "[*] Test des configurations..."
suricata -T -c /etc/suricata/suricata.yaml -v >/dev/null 2>&1 && echo "    Suricata : OK" || echo "    Suricata : ERREUR (lance: sudo suricata -T -c /etc/suricata/suricata.yaml -v)"
snort -T -c /etc/snort/snort.conf -i "$IFACE" >/dev/null 2>&1 && echo "    Snort    : OK" || echo "    Snort    : ERREUR (lance: sudo snort -T -c /etc/snort/snort.conf -i $IFACE)"

echo "$IFACE" > "$REPO_DIR/.iface"
echo "[+] Terminé. Étape suivante :  sudo ./scripts/lab.sh ips"
