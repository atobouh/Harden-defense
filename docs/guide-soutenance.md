# Guide de soutenance : comment expliquer Harden Defense

## 1. Le projet en 30 secondes

> « J'ai monté un laboratoire de cybersécurité avec deux machines virtuelles : **Kali** qui attaque et **Ubuntu** qui se défend.
> Ubuntu fait tourner deux sondes sur le même trafic : **Snort**, un IDS qui détecte et alerte, et **Suricata**, un IPS qui détecte
> **et bloque**. Je lance 4 attaques depuis Kali, et mon tableau de bord montre ce que chaque sonde a vu et ce que l'attaquant a
> réellement obtenu. Les alertes sont enregistrées dans une base SQL, expliquées par une IA et envoyées sur Telegram. »

## 2. Les mots à maîtriser

| Terme | Une phrase |
|---|---|
| **IDS** | Détecte et prévient. Il regarde une copie du trafic, il ne peut rien arrêter. |
| **IPS** | Détecte et bloque. Le trafic passe *par lui* : il peut jeter un paquet avant qu'il arrive. |
| **Signature (règle)** | Une description d'attaque connue (« 20 SYN en 5 s », « UNION SELECT dans l'URL »). |
| **Faux positif** | Du trafic normal pris pour une attaque. Dangereux surtout pour un IPS (il coupe un vrai utilisateur). |
| **NFQUEUE** | Mécanisme Linux qui envoie chaque paquet à un programme (Suricata) qui décide : laisser passer ou jeter. |
| **SQLite** | Base de données SQL contenue dans un seul fichier. |

## 3. Chaque partie du projet

| Partie | Ce qu'elle fait | Où |
|---|---|---|
| Règles | Décrivent les 4 attaques, identiques pour les deux sondes (comparaison équitable) | `config/` |
| `lab.sh` | Mode `ids` : tout le monde observe. Mode `ips` : `iptables` envoie les paquets à Suricata, qui jette les attaques | `scripts/lab.sh` |
| Collecteur | Lit les journaux des deux sondes, les met au même format, les enregistre en SQLite. Regroupe 500 paquets d'un scan en **un incident** | `harden/collector.py`, `parsers.py`, `db.py` |
| Base SQL | 4 tables : `alerts`, `analyses`, `attack_results`, `offsets` | `harden/db.py` |
| IA | Explique chaque type d'attaque en français et donne un conseil. Les demandes sont groupées **par lots** (jusqu'à 20 dans une requête) pour respecter la limite gratuite ; modèle de secours, puis texte intégré si besoin. Rien n'attend l'IA. | `harden/analyzer.py` |
| Réglages | Page qui teste puis enregistre la clé de l'IA et guide la connexion Telegram en 3 étapes ; les secrets ne sont jamais renvoyés au navigateur | `harden/dashboard.py`, `static/settings.js` |
| Telegram | Envoie l'alerte (⛔ bloquée ou 👁 détectée) avec l'analyse | `harden/telegram.py` |
| Dashboard | Page web qui lit la base et se rafraîchit toute seule | `harden/dashboard.py`, `static/` |
| `attack.sh` | Lance les attaques depuis Kali (ou depuis l'attaquant intégré) et mesure si elles passent | `kali/attack.sh` |
| Mode une machine | `lab-net.sh` crée un **câble virtuel** (`veth`) entre la machine (`10.88.0.1`) et un **espace réseau isolé** (`hdlab`, `10.88.0.2`) où vit l'attaquant. Il a sa propre carte réseau et ne voit rien d'autre : c'est exactement comme une 2e machine. `labd.py` (droits administrateur) est le seul à pouvoir changer de mode ou lancer les attaques ; le dashboard, lui, n'a pas ces droits et lui envoie des **ordres d'une liste fermée** par un socket réservé | `install.sh`, `scripts/lab-net.sh`, `harden/labd.py`, `labctl.py` |

Requêtes SQL à montrer (ouvrir la base : `sqlite3 data/harden.db`) :

```sql
-- Top des IP attaquantes
SELECT src_ip, SUM(hits) AS paquets FROM alerts GROUP BY src_ip ORDER BY paquets DESC;
-- Ce que chaque sonde a vu, par attaque
SELECT signature, engine, action, COUNT(*) FROM alerts GROUP BY signature, engine, action;
-- Verdict de Kali dans chaque mode
SELECT scenario, mode, success, detail FROM attack_results ORDER BY ts;
```

## 4. Lire le dashboard (30 secondes, sans jargon)

Le dashboard montre d'abord l'essentiel, le reste s'ouvre **à la demande** :

- **Au premier regard** : un grand titre qui répond à « suis-je en sécurité ? » (vert = tout est arrêté, orange = des attaques sont passées), le mode actif (*Surveillance* : on observe et on prévient ; *Protection* : on bloque) et trois chiffres. Le graphique d'activité est derrière « Voir l'activité ».
- **Quatre vues, une seule à la fois** (onglets ; en bas de l'écran sur téléphone) :
  - **Attaques** : un tableau de trois colonnes, *Pas encore vue → Repérée, mais passée → Arrêtée*. Une carte = un type d'attaque ; on la touche pour voir ses deux verdicts (Surveillance, Protection). Un badge orange signale les attaques passées.
  - **Alertes** : une phrase par alerte ; un clic ouvre l'explication, le conseil et le détail technique. Un point bleu signale une nouvelle alerte.
  - **Sources** : les machines à l'origine des attaques.
  - **Gardiens** : Snort le guetteur (IDS) et Suricata le videur (IPS).

## 5. Démonstration en 5 minutes

*(Version « une machine » : tout se fait dans le dashboard. Version deux VM, ci-dessous.)*
Sur le dashboard : **Lancer la démonstration** en Surveillance (4 attaques passées, toutes repérées), puis clic sur **Protection**, **Lancer la démonstration** (4 attaques arrêtées). Le reste est identique.

**Version deux VM :**

1. `sudo ./scripts/lab.sh ids` puis ouvrir le dashboard. *« Mode IDS : on observe seulement. »*
2. Sur Kali : `./attack.sh IP all http://IP:5000`. Les 4 attaques sont **passées**, mais détectées par les deux sondes.
3. `sudo ./scripts/lab.sh ips`, relancer `attack.sh`. Les 4 attaques sont **bloquées**.
4. Montrer les cartes qui ont **glissé** de « Repérée, mais passée » vers « Arrêtée » (chaque carte garde ses deux verdicts), puis le message Telegram.
5. Conclure : *« L'IDS me dit qu'on m'attaque, l'IPS empêche l'attaque. »*

## 6. Résultats mesurés (laboratoire de développement)

Mesures faites pendant le développement sur un banc d'essai simulé (Kali dans un espace réseau isolé, Suricata 7.0.3, Snort 2.9.20).
**Refais-les sur tes VM et remplace ce tableau par tes propres chiffres.**

| Attaque | Mode IDS | Mode IPS |
|---|---|---|
| Scan de ports (500 ports) | passée, 0/500 sans réponse | étouffée : 440/500 sans réponse (mais 2 ports ouverts entrevus) |
| Bruteforce SSH (15 connexions) | 15/15 répondues | 5/15 répondues |
| Flood ICMP (60 pings) | 0 % de pertes | environ 50 % de pertes |
| Injection SQL | HTTP 200 | aucune réponse (connexion coupée) |
| Trafic normal (ping, web, SSH) | 3/3 | 3/3 : **aucun faux positif** |

## 7. Les limites : le dire soi-même est un point fort

- **Détection par signatures** : on ne détecte que ce qu'on a décrit. Un attaquant lent ou une attaque inconnue passe. Piste d'amélioration : détection d'anomalies par machine learning.
- **Seuils** : l'IPS laisse passer les premiers paquets avant le seuil. Exemple vu en test : nmap sonde d'abord les ports courants (22, 80), donc il les *entrevoit* avant d'être coupé.
- **Une seule machine** : Snort et Suricata tournent sur la même machine que la cible. En vrai, on placerait l'IPS devant le réseau (en passerelle) et l'IDS sur un port miroir.
- **Pas de chiffrement** : le contenu HTTPS ne peut pas être lu par ces règles.
- **Lab, pas production** : le dashboard n'a pas d'authentification.

## 8. Questions probables du jury

**Pourquoi deux outils ?** Pour *voir* la différence entre détecter (Snort, IDS) et bloquer (Suricata, IPS) sur les mêmes attaques.

**Pourquoi un IPS peut-il être dangereux ?** Un faux positif coupe du trafic légitime. C'est pourquoi `attack.sh` commence par un contrôle de trafic normal.

**Pourquoi pas un vrai Kali dans ce mode ?** Un espace réseau isolé (*network namespace*) se comporte comme une machine séparée : son adresse, sa carte, sa table de routage. Les paquets traversent le même chemin que ceux d'une vraie 2e machine, donc les sondes voient exactement la même chose. Le laboratoire à deux VM reste disponible pour montrer un vrai Kali.

**Est-ce sûr d'avoir un bouton qui lance des attaques ?** Les attaques ne visent que `10.88.0.1`, la machine elle-même, depuis un compte sans droits (`harden-attacker`, seul `nmap` est autorisé en administrateur). Le dashboard n'accepte l'ordre que de la machine locale (ou avec un code à 6 chiffres), vérifie l'origine de la requête, et le programme qui exécute n'accepte qu'une liste fermée de commandes.

**Où est l'intelligence ?** L'IA (Gemini ou Claude) analyse chaque type d'alerte comme un analyste SOC (explication, gravité, conseil). Les demandes sont envoyées par lots pour rester sous la limite gratuite (15 requêtes par minute), et sans IA l'application fonctionne quand même. La détection elle-même reste à base de règles ; le machine learning est la suite logique du projet.

**À quoi sert la base SQL ?** À garder l'historique et à produire les statistiques (top attaquants, comparaison des sondes).

**Qu'as-tu fait toi-même ?** Montage du labo, règles, tests des attaques, analyse des résultats. *(Le projet a été développé avec l'aide d'une IA ; dis-le franchement, et sois capable d'expliquer chaque fichier grâce à ce guide.)*

## 9. Plan possible pour le rapport

1. Contexte et objectifs (IDS contre IPS) ; 2. Architecture du labo (schéma + captures VirtualBox) ;
3. Installation et configuration (Snort, Suricata, règles) ; 4. Scénarios d'attaque ; 5. Résultats (tableau + captures du dashboard + Telegram) ;
6. Analyse et limites ; 7. Perspectives (machine learning, placement réseau réaliste, plus de règles).
