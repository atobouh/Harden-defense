#!/usr/bin/env bash
# Harden Defense : installation complète en UNE commande, sur UNE seule machine Ubuntu.
#
#     sudo ./install.sh
#
# Ce que ça fait (rien à faire de ton côté, aucune question n'est posée) :
#   1. installe Snort, Suricata, Apache, SSH, nmap, Python ;
#   2. crée un petit réseau interne avec une machine « attaquante » isolée (c'est elle qui remplace Kali) ;
#   3. configure les sondes avec les règles du projet ;
#   4. installe le dashboard et le démarre automatiquement, à chaque démarrage de l'ordinateur.
# Ensuite : http://localhost:5000
#
# Options (inutiles en usage normal) :  --no-systemd (tests/conteneur)   --prefix DOSSIER
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HD_PREFIX:-/opt/harden-defense}"
STATE=/var/lib/harden-defense
LOG=/var/log/harden-install.log
SYSTEMD=auto
while [ $# -gt 0 ]; do
  case "$1" in
    --no-systemd) SYSTEMD=no ;;
    --prefix) PREFIX="${2:?--prefix attend un dossier}"; shift ;;
    -h|--help) sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 2 ;;
  esac
  shift
done

B=$'\e[1m'; G=$'\e[32m'; R=$'\e[31m'; D=$'\e[2m'; N=$'\e[0m'
[ "$EUID" -eq 0 ] || { echo "${D}(sudo est nécessaire pour installer les sondes : on te demande ton mot de passe une seule fois)${N}"; exec sudo -E bash "$0" "$@"; }

command -v apt-get >/dev/null || { echo "${R}Ce script est prévu pour Ubuntu/Debian (apt-get introuvable).${N}"; exit 1; }
if [ "$SYSTEMD" = auto ]; then [ -d /run/systemd/system ] && SYSTEMD=yes || SYSTEMD=no; fi
OWNER="${SUDO_USER:-}"; [ "$OWNER" = root ] && OWNER=""

mkdir -p "$(dirname "$LOG")"; : > "$LOG"
TOTAL=7; n=0
step() { n=$((n+1)); echo "${B}[$n/$TOTAL]${N} $1"; }
fail() { echo; echo "${R}${B}L'installation s'est arrêtée.${N} $1"; echo "Les dernières lignes du journal ($LOG) :"; tail -n 12 "$LOG" | sed 's/^/    /'; exit 1; }
run() { "$@" >>"$LOG" 2>&1 || fail "Commande en échec : $*"; }
# Les téléchargements peuvent échouer (réseau instable) : on réessaie 3 fois avant d'abandonner, sans rien retélécharger de ce qui est déjà là.
retry() { local i; for i in 1 2 3; do "$@" >>"$LOG" 2>&1 && return 0; echo "    (réseau instable, nouvel essai $i/3…)"; dpkg --configure -a >>"$LOG" 2>&1 || true; sleep 5; done; fail "Commande en échec : $*"; }
APT_OPTS=(-o Acquire::Languages=none -o Acquire::Retries=5)
trap 'fail "Erreur inattendue (ligne $LINENO)."' ERR

echo
echo "${B}Harden Defense${N} — installation automatique ${D}(10 à 15 minutes, surtout du téléchargement)${N}"
echo

# ---------------------------------------------------------------- 1
step "Téléchargement des outils (Snort, Suricata, Apache, SSH, nmap, Python)…"
export DEBIAN_FRONTEND=noninteractive
# --no-install-recommends et pas de traductions : on ne télécharge que le strict nécessaire.
retry apt-get update -y "${APT_OPTS[@]}"
retry apt-get install -y --no-install-recommends "${APT_OPTS[@]}" ca-certificates curl iproute2 iptables iputils-ping util-linux sudo nmap \
    python3 python3-venv rsync openssh-server apache2

# ---------------------------------------------------------------- 2
step "Création des comptes techniques et des dossiers…"
getent group harden >/dev/null || run groupadd --system harden
id harden >/dev/null 2>&1 || run useradd --system --gid harden --no-create-home --shell /usr/sbin/nologin harden
id harden-attacker >/dev/null 2>&1 || run useradd --system --no-create-home --shell /usr/sbin/nologin harden-attacker
[ -z "$OWNER" ] || run usermod -aG harden "$OWNER"
install -d -m 755 "$PREFIX"
install -d -m 755 -o harden -g harden "$STATE"
# L'attaquant isolé n'a le droit de lancer QUE nmap (scan SYN) avec les droits administrateur.
NMAP="$(command -v nmap)"
echo "harden-attacker ALL=(root) NOPASSWD: $NMAP" > /etc/sudoers.d/harden-attacker
chmod 440 /etc/sudoers.d/harden-attacker
run visudo -cf /etc/sudoers.d/harden-attacker
[ -f /etc/default/harden-defense ] || printf '# Réglages avancés (facultatif)\n%s\n' "${HD_TRUSTED:+TRUSTED_ADDRS=$HD_TRUSTED}" > /etc/default/harden-defense

if [ "$SRC" != "$PREFIX" ]; then
  run rsync -a --delete --exclude .git --exclude .venv --exclude data --exclude docs --exclude tests --exclude __pycache__ \
        --exclude .env --exclude .iface --exclude .ruff_cache --exclude '*.db' "$SRC"/ "$PREFIX"/
fi
sed "s|@PREFIX@|$PREFIX|g" "$PREFIX/scripts/harden" > /usr/local/bin/harden
chmod 755 /usr/local/bin/harden "$PREFIX"/scripts/*.sh "$PREFIX"/kali/attack.sh "$PREFIX"/uninstall.sh

# ---------------------------------------------------------------- 3
step "Création du réseau interne (la machine attaquante isolée)…"
modprobe nfnetlink_queue >>"$LOG" 2>&1 || true
run "$PREFIX/scripts/lab-net.sh" up
# Ubuntu Desktop : NetworkManager ne doit pas toucher à la carte virtuelle du laboratoire.
if [ -d /etc/NetworkManager/conf.d ]; then
  printf '[keyfile]\nunmanaged-devices=interface-name:hd0\n' > /etc/NetworkManager/conf.d/harden-defense.conf
  nmcli general reload conf >>"$LOG" 2>&1 || true
fi

# ---------------------------------------------------------------- 4
step "Installation et réglage de Snort et Suricata…"
"$PREFIX/scripts/install_defender.sh" hd0 >>"$LOG" 2>&1 || fail "Le réglage des sondes a échoué."
grep -q "ERREUR" "$LOG" && fail "Une sonde refuse sa configuration."
echo hd0 > "$PREFIX/.iface"

# ---------------------------------------------------------------- 5
step "Réglage du serveur web (il ne répond que dans le laboratoire, pas sur ton réseau)…"
if [ -f /etc/apache2/ports.conf ]; then
  [ -f /etc/apache2/ports.conf.hd-bak ] || cp /etc/apache2/ports.conf /etc/apache2/ports.conf.hd-bak
  sed -i -E 's/^Listen 80$/Listen 10.88.0.1:80/' /etc/apache2/ports.conf
fi

# ---------------------------------------------------------------- 6
step "Installation du dashboard…"
run python3 -m venv "$PREFIX/.venv"
retry "$PREFIX/.venv/bin/pip" install --quiet --disable-pip-version-check -r "$PREFIX/requirements.txt"
cat > /usr/share/applications/harden-defense.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Harden Defense
Comment=Dashboard de défense IDS/IPS
Exec=xdg-open http://localhost:5000
Icon=security-high
Terminal=false
Categories=Network;Security;
EOF

# ---------------------------------------------------------------- 7
step "Démarrage automatique des services…"
if [ "$SYSTEMD" = yes ]; then
  for u in harden-lab harden-dashboard harden-collector; do
    sed "s|@PREFIX@|$PREFIX|g" "$PREFIX/systemd/$u.service" > "/etc/systemd/system/$u.service"
  done
  install -d /etc/systemd/system/apache2.service.d
  install -m 644 "$PREFIX/systemd/apache2-after-lab.conf" /etc/systemd/system/apache2.service.d/harden.conf
  run systemctl daemon-reload
  run systemctl enable ssh apache2 harden-lab harden-collector harden-dashboard
  run systemctl restart ssh
  run systemctl restart harden-lab harden-collector harden-dashboard
  run systemctl restart apache2
else
  mkdir -p /run/sshd
  service ssh start >>"$LOG" 2>&1 || true
  service apache2 restart >>"$LOG" 2>&1 || apachectl start >>"$LOG" 2>&1 || true
  HD_PREFIX="$PREFIX" run "$PREFIX/scripts/services.sh" stop
  HD_PREFIX="$PREFIX" run "$PREFIX/scripts/services.sh" start
fi

printf "    en attente du dashboard"
ready=""
for _ in $(seq 60); do
  if curl -sf -m 2 http://127.0.0.1:5000/api/lab 2>/dev/null | grep -q '"available": *true'; then ready=1; break; fi
  printf "."; sleep 2
done
echo
trap - ERR
[ -n "$ready" ] || fail "Le dashboard ne répond pas. Regarde : harden logs"

# Le mode choisi au premier démarrage est « Surveillance » ; on attend que les sondes aient démarré.
for _ in $(seq 40); do
  curl -sf -m 2 http://127.0.0.1:5000/api/lab | grep -q '"busy": *null' && break
  sleep 2
done

touch "$STATE/.installed"      # repère : un « vagrant up » ultérieur ne refait pas l'installation
echo
echo "${G}${B}✔ Installation terminée.${N}"
echo
echo "   Dashboard :  ${B}http://localhost:5000${N}   ${D}(il démarre tout seul à chaque allumage de l'ordinateur)${N}"
echo "   Dans la page, clique sur ${B}« Lancer la démonstration »${N}, puis passe de ${B}Surveillance${N} à ${B}Protection${N} et relance."
echo "   Terminal : ${B}harden${N} status | ids | ips | demo | open | uninstall"
if [ -n "$OWNER" ]; then
  echo "   ${D}(ferme puis rouvre ton terminal une fois : ton compte vient d'être ajouté au groupe « harden »)${N}"
  sudo -u "$OWNER" -E xdg-open http://localhost:5000 >/dev/null 2>&1 &
fi
echo
