# Installer Harden Defense sur ton ordinateur

Deux façons de l'utiliser. Commence par la **A** (10 minutes), elle te montre tout de suite à quoi ça ressemble.
Passe à la **B** pour le vrai laboratoire (1 à 2 heures la première fois).

| | **A. Voir le dashboard** | **B. Le vrai laboratoire** |
|---|---|---|
| Ce que tu obtiens | Le tableau de bord avec des données de démonstration | Snort et Suricata qui détectent et bloquent de vraies attaques |
| Ce qu'il faut | Python | VirtualBox + 2 machines virtuelles (Ubuntu et Kali) |
| Pour qui | Découvrir, préparer le rapport, tester Telegram et l'IA | La démonstration et la soutenance |

---

## A. Voir le dashboard (Windows, Mac ou Linux)

**1. Installe Python** (version 3.10 ou plus récente) depuis <https://www.python.org/downloads/>.
Sous Windows, coche **« Add Python to PATH »** pendant l'installation.

**2. Récupère le projet.** Soit avec git : `git clone https://github.com/atobouh/Harden-defense.git`,
soit sur GitHub avec le bouton vert **Code → Download ZIP**, puis décompresse-le.

**3. Ouvre un terminal dans le dossier du projet** (Windows : clic droit dans le dossier → « Ouvrir dans le terminal »), puis :

*Windows (PowerShell)*
```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m harden.demo --reset
.venv\Scripts\python -m harden.dashboard
```

*Mac / Linux*
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m harden.demo --reset
.venv/bin/python -m harden.dashboard
```

**4. Ouvre <http://localhost:5000>** dans ton navigateur. Pour arrêter : `Ctrl + C` dans le terminal.

C'est tout. Tu peux déjà aller dans l'onglet **Réglages** pour brancher Telegram et l'IA (voir plus bas).

---

## B. Le vrai laboratoire avec VirtualBox

### Ce qu'il te faut
- Un ordinateur avec **8 Go de mémoire** au minimum (16 Go, c'est confortable) et 40 Go de disque libre.
- [VirtualBox](https://www.virtualbox.org/wiki/Downloads) (gratuit).
- L'image d'**Ubuntu** (22.04 ou 24.04) : <https://ubuntu.com/download/desktop>.
- L'image de **Kali Linux** : <https://www.kali.org/get-kali/> (prends « Virtual Machines », elle est déjà installée).

### Étape 1 : un réseau privé entre les deux machines
Dans VirtualBox : **Fichier → Outils → Gestionnaire de réseau → Réseaux hôtes uniquement → Créer**, et active le **serveur DHCP**.
C'est le câble virtuel entre Kali et Ubuntu (et ton ordinateur y est branché aussi, pour ouvrir le dashboard).

### Étape 2 : régler les deux machines
Pour **chaque** machine (Ubuntu et Kali) : **Configuration → Réseau**
- **Carte 1** : *NAT* (pour avoir internet et installer les programmes).
- **Carte 2** : *Réseau privé hôte* (le réseau que tu viens de créer).

Ubuntu : 4 Go de mémoire, 2 processeurs. Kali : 2 Go, 2 processeurs.

### Étape 3 : installer sur Ubuntu (le défenseur)
Démarre Ubuntu, ouvre un terminal, puis :
```bash
ip a                                   # note le nom de la 2e carte (souvent enp0s8) et son IP (192.168.56.xxx)
sudo apt update && sudo apt install -y git
git clone https://github.com/atobouh/Harden-defense.git
cd Harden-defense
sudo ./scripts/install_defender.sh enp0s8      # remplace enp0s8 par le nom de TA 2e carte
./scripts/install_app.sh
```
L'installation dure quelques minutes. À la fin, les deux lignes `Suricata : OK` et `Snort : OK` doivent apparaître.

### Étape 4 : démarrer le laboratoire
Dans le terminal d'Ubuntu :
```bash
sudo ./scripts/lab.sh ids          # mode Surveillance : on observe, on ne bloque rien
```
Dans un **deuxième** terminal d'Ubuntu :
```bash
cd Harden-defense && ./scripts/run_app.sh
```
Le terminal affiche l'adresse du dashboard et un **code à 6 chiffres** (utile pour les réglages à distance).
Depuis **ton ordinateur**, ouvre `http://192.168.56.xxx:5000` (l'IP d'Ubuntu).

### Étape 5 : attaquer depuis Kali
Démarre Kali, ouvre un terminal :
```bash
git clone https://github.com/atobouh/Harden-defense.git && cd Harden-defense/kali
./attack.sh 192.168.56.xxx all http://192.168.56.xxx:5000
```
(Remplace `192.168.56.xxx` par l'IP d'Ubuntu.) Regarde le dashboard : les attaques sont **passées** mais repérées.

### Étape 6 : passer en mode Protection
Sur Ubuntu : `sudo ./scripts/lab.sh ips`, puis relance `./attack.sh …` depuis Kali.
Les cartes du dashboard glissent de « Repérée, mais passée » vers « **Arrêtée** ». C'est la démonstration.

---

## Brancher Telegram et l'IA (dans la page Réglages)

Ouvre l'onglet **Réglages** du dashboard. Rien n'est obligatoire.

**Telegram (3 étapes guidées)**
1. Dans Telegram, ouvre **@BotFather**, envoie `/newbot`, réponds aux deux questions. Il te donne un *token* : colle-le dans la page, clique **Connecter**.
2. Ouvre ton bot dans Telegram, envoie-lui `/start`, puis clique **Trouver mon compte**.
3. Clique **Envoyer un message de test** : il arrive sur ton téléphone.

**L'IA (gratuite avec Gemini)**
1. Va sur <https://aistudio.google.com/apikey>, connecte-toi avec ton compte Google, crée une clé.
2. Colle-la dans la page, choisis **Gemini**, clique **Tester et enregistrer**. Si la clé fonctionne, elle est enregistrée ; sinon, un message t'explique quoi corriger.

Les explications sont demandées par lots pour rester sous la limite gratuite de Google (15 requêtes par minute) ; si la limite est atteinte,
l'application réessaie toute seule et garde les textes intégrés en attendant.

> **Réglages depuis un autre appareil.** Depuis l'ordinateur où tourne l'application, aucun code n'est demandé. Depuis un autre appareil
> (ton PC quand l'application tourne dans la VM Ubuntu), la page te demande le **code à 6 chiffres** affiché dans le terminal.
> Sans ce code, personne d'autre sur le réseau ne peut modifier tes clés.

---

## Ça ne marche pas ?

| Symptôme | Que faire |
|---|---|
| `python` introuvable sous Windows | Réinstalle Python en cochant « Add Python to PATH », ou utilise `py` à la place de `python`. |
| Le dashboard est vide (mode B) | Vérifie `sudo ./scripts/lab.sh status` et que `run_app.sh` tourne. Lance une attaque depuis Kali. |
| Kali n'atteint pas Ubuntu | `ping 192.168.56.xxx` depuis Kali. Vérifie que les deux machines ont la carte 2 en *Réseau privé hôte*. |
| L'ordinateur n'atteint pas le dashboard | Utilise l'IP de la 2e carte d'Ubuntu (`ip a`), pas celle du NAT (10.0.2.x). |
| « Clé refusée » | Recopie la clé en entier, sans espace. Crée-en une nouvelle dans AI Studio si besoin. |
| « Limite gratuite atteinte » | Attends une minute : l'application réessaie seule. Elle utilise un modèle de secours entre-temps. |
| Telegram : « Rien reçu pour l'instant » | Ouvre ton bot dans Telegram, envoie-lui `/start`, puis reclique sur **Trouver mon compte**. |
| Suricata affiche `ERREUR` à l'installation | `sudo suricata -T -c /etc/suricata/suricata.yaml -v` montre la ligne en cause. |

**Mettre à jour le projet** : `git pull` dans le dossier, puis relance `./scripts/run_app.sh`.

**N'attaque que tes propres machines virtuelles.**
