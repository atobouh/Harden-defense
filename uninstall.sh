#!/usr/bin/env bash
# Désinstalle Harden Defense (services, réseau interne, règles pare-feu, fichiers). Les paquets Snort/Suricata/Apache restent installés.
#     sudo harden uninstall        ou        sudo ./uninstall.sh
set -uo pipefail
[ "$EUID" -eq 0 ] || exec sudo -E bash "$0" "$@"
main() {
PREFIX="${HD_PREFIX:-/opt/harden-defense}"; [ -d "$PREFIX/scripts" ] || PREFIX="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE=/var/lib/harden-defense

echo "[*] Arrêt des services…"
if [ -d /run/systemd/system ]; then
  systemctl disable --now harden-dashboard harden-collector harden-lab 2>/dev/null || true
  rm -f /etc/systemd/system/harden-{lab,dashboard,collector}.service
  rm -rf /etc/systemd/system/apache2.service.d/harden.conf
  systemctl daemon-reload
else
  "$PREFIX/scripts/services.sh" stop 2>/dev/null || true
fi
"$PREFIX/scripts/lab.sh" stop >/dev/null 2>&1 || true
"$PREFIX/scripts/lab-net.sh" down >/dev/null 2>&1 || true

echo "[*] Remise en état d'Apache…"
[ -f /etc/apache2/ports.conf.hd-bak ] && mv /etc/apache2/ports.conf.hd-bak /etc/apache2/ports.conf
service apache2 restart >/dev/null 2>&1 || true

echo "[*] Suppression des fichiers et des comptes techniques…"
rm -f /usr/local/bin/harden /usr/share/applications/harden-defense.desktop /etc/sudoers.d/harden-attacker /etc/default/harden-defense /etc/NetworkManager/conf.d/harden-defense.conf
rm -rf "$STATE" /var/log/harden /run/harden
userdel harden-attacker 2>/dev/null || true
userdel harden 2>/dev/null || true
groupdel harden 2>/dev/null || true
cd / || true
# on ne supprime jamais un dossier qui est une copie de travail git (celle que tu as téléchargée)
[ -d "$PREFIX/.git" ] || rm -rf "$PREFIX"
echo "[+] Désinstallé. (Pour retirer aussi les logiciels : sudo apt remove --purge snort suricata)"
}
main "$@"
exit $?
