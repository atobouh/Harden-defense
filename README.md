# Harden Defense

**Un mini-SOC de laboratoire** : une machine attaque, une autre se défend, et un tableau de bord montre
en direct **la différence entre un IDS (qui prévient) et un IPS (qui bloque)**.

![Dashboard en mode protection](docs/dashboard.png)
![Dashboard en mode surveillance](docs/dashboard-ids.png)
<sub>Les deux modes, avec des données de démonstration (`python -m harden.demo`). Affichage progressif : on voit d'abord la situation, puis l'utilisateur choisit ce qu'il veut approfondir (Attaques, Alertes, Sources, Gardiens). Sur téléphone, les onglets sont en bas de l'écran.</sub>

```
  Kali Linux (attaquant)  ──►  Ubuntu (défenseur)
                                 ├─ Snort     = IDS : observe et ALERTE
                                 ├─ Suricata  = IPS : observe et BLOQUE
                                 ├─ Collecteur Python ─► base SQLite ─► Dashboard web
                                 ├─ Analyse de chaque alerte par une IA (optionnelle)
                                 └─ Alertes Telegram (optionnelles)
```

| Dossier | Contenu |
|---|---|
| `config/` | Les règles de détection (Snort et Suricata, mêmes attaques) |
| `scripts/` | Installation et pilotage du labo (`install_defender.sh`, `lab.sh`, `run_app.sh`…) |
| `kali/attack.sh` | Les 4 attaques à lancer depuis Kali |
| `harden/` | L'application Python : collecteur, base SQL, IA, Telegram, dashboard |
| `docs/` | `ids-vs-ips.md` (le concept) et `guide-soutenance.md` (comment tout expliquer) |

## Ce qu'on détecte

| Attaque | Outil Kali | Règle |
|---|---|---|
| Scan de ports | `nmap -sS` | 20 SYN en 5 s depuis la même IP |
| Bruteforce SSH | connexions répétées | 5 connexions au port 22 en 30 s |
| Flood ICMP | `ping` en rafale | 20 pings en 5 s |
| Injection SQL | `curl` avec `UNION SELECT` / `OR 1=1` | contenu de la requête HTTP |

## Installation

### 0. Les deux machines (VirtualBox)

Chaque VM doit avoir **deux cartes réseau** :
1. **NAT** (accès internet, pour installer les paquets) ;
2. **Réseau privé hôte** (*Host-only*) : c'est le réseau du labo, Kali et Ubuntu s'y voient, et ton navigateur aussi.

Vérifie avec `ip a` puis `ping` entre les deux VM. Note l'IP d'Ubuntu sur le réseau privé (souvent `192.168.56.x`)
et le nom de sa carte (souvent `enp0s8`).

### 1. Sur Ubuntu (le défenseur)

```bash
git clone https://github.com/atobouh/Harden-defense.git
cd Harden-defense

sudo ./scripts/install_defender.sh enp0s8   # Snort, Suricata, apache2, ssh ; remplace enp0s8 par ta carte du réseau privé
./scripts/install_app.sh                    # dashboard + collecteur (sans sudo)
```

### 2. Démarrer

```bash
sudo ./scripts/lab.sh ids        # 1) mode détection : rien n'est bloqué
./scripts/run_app.sh             # 2) dans un 2e terminal : collecteur + dashboard
```

Ouvre **`http://IP_UBUNTU:5000`** dans le navigateur de ton PC.

### 3. Sur Kali (l'attaquant)

```bash
git clone https://github.com/atobouh/Harden-defense.git && cd Harden-defense/kali
./attack.sh IP_UBUNTU all http://IP_UBUNTU:5000
```

Le script lance le contrôle « trafic normal » puis les 4 attaques, dit pour chacune si elle est **passée** ou
**bloquée**, et envoie le verdict au dashboard.

### 4. La comparaison IDS contre IPS

```bash
sudo ./scripts/lab.sh ips        # sur Ubuntu : Suricata se met à bloquer
```

Relance `./attack.sh …` depuis Kali : les cartes du dashboard **changent de colonne** : de « Repérée, mais passée » vers « Arrêtée ». Chaque carte garde
les deux verdicts (*Surveillance* puis *Protection*). C'est le cœur de la démonstration.

Autres commandes : `sudo ./scripts/lab.sh status` · `sudo ./scripts/lab.sh stop`

## Options (facultatives)

Tout fonctionne sans, configure-les dans `.env` (voir `.env.example`, il explique chaque étape) :

- **Telegram** : un message par alerte, avec l'analyse. Test : `.venv/bin/python -m harden.telegram test`.
- **IA** : avec une clé API Claude, chaque type d'attaque est expliqué par l'IA (une seule fois, puis gardé en base).
  Sans clé, des explications intégrées sont utilisées.

## Voir le dashboard sans lancer les VM

```bash
.venv/bin/python -m harden.demo --reset
.venv/bin/python -m harden.dashboard      # http://localhost:5000
```

## Tests automatiques

```bash
python3 -m unittest discover -s tests -v
```

## Modifier une règle

Édite `config/snort/local.rules` et `config/suricata/local.rules`, puis `sudo ./scripts/install_defender.sh enp0s8`
et `sudo ./scripts/lab.sh ips`.

## Sécurité

- Projet **pédagogique, pour un réseau de laboratoire isolé** : le dashboard n'a pas de mot de passe. Ne l'expose pas sur internet.
- `.env` (token Telegram, clé API) est ignoré par git : ne le publie jamais.
- N'attaque que **tes propres machines**.

## Problèmes fréquents

| Symptôme | Solution |
|---|---|
| `Suricata : ERREUR` à l'installation | `sudo suricata -T -c /etc/suricata/suricata.yaml -v` affiche la ligne en cause |
| Snort ne génère aucune alerte | Vérifie la carte réseau (`ip a`) et relance `install_defender.sh <carte>`. `lab.sh` lance déjà Snort avec `-k none` (sommes de contrôle ignorées : sinon, sur VM, Snort peut rester muet) |
| Kali ne répond plus après une attaque en mode IPS | Normal : l'IPS l'a bloqué quelques secondes (les compteurs se remettent à zéro) |
| Le dashboard est vide | `sudo ./scripts/lab.sh status`, et lance `./scripts/run_app.sh` |
