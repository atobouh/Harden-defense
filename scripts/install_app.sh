#!/usr/bin/env bash
# À lancer UNE FOIS sur la VM Ubuntu (sans sudo) : prépare Python + le dashboard.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo "python3 est requis : sudo apt install python3 python3-venv"; exit 1; }
python3 -m venv .venv 2>/dev/null || { echo "Installe d'abord : sudo apt install -y python3-venv"; exit 1; }
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "[*] Fichier .env créé (à compléter pour Telegram / IA, sinon ça marche quand même)."; }
mkdir -p data
echo "[+] Application prête. Lance-la avec :  ./scripts/run_app.sh"
