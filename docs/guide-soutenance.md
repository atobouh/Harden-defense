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
| IA | Explique chaque type d'attaque en français et donne un conseil. Appelée une seule fois par type (coût minimal), avec explications de secours si pas de clé | `harden/analyzer.py` |
| Telegram | Envoie l'alerte (⛔ bloquée ou 👁 détectée) avec l'analyse | `harden/telegram.py` |
| Dashboard | Page web qui lit la base et se rafraîchit toute seule | `harden/dashboard.py`, `static/` |
| `attack.sh` | Lance les attaques depuis Kali et mesure si elles passent | `kali/attack.sh` |

Requêtes SQL à montrer (ouvrir la base : `sqlite3 data/harden.db`) :

```sql
-- Top des IP attaquantes
SELECT src_ip, SUM(hits) AS paquets FROM alerts GROUP BY src_ip ORDER BY paquets DESC;
-- Ce que chaque sonde a vu, par attaque
SELECT signature, engine, action, COUNT(*) FROM alerts GROUP BY signature, engine, action;
-- Verdict de Kali dans chaque mode
SELECT scenario, mode, success, detail FROM attack_results ORDER BY ts;
```

## 4. Démonstration en 5 minutes

1. `sudo ./scripts/lab.sh ids` puis ouvrir le dashboard. *« Mode IDS : on observe seulement. »*
2. Sur Kali : `./attack.sh IP all http://IP:5000`. Les 4 attaques sont **passées**, mais détectées par les deux sondes.
3. `sudo ./scripts/lab.sh ips`, relancer `attack.sh`. Les 4 attaques sont **bloquées**.
4. Montrer le tableau « Même attaque, deux résultats », puis le message Telegram.
5. Conclure : *« L'IDS me dit qu'on m'attaque, l'IPS empêche l'attaque. »*

## 5. Résultats mesurés (laboratoire de développement)

Mesures faites pendant le développement sur un banc d'essai simulé (Kali dans un espace réseau isolé, Suricata 7.0.3, Snort 2.9.20).
**Refais-les sur tes VM et remplace ce tableau par tes propres chiffres.**

| Attaque | Mode IDS | Mode IPS |
|---|---|---|
| Scan de ports (500 ports) | passée, 0/500 sans réponse | étouffée : 440/500 sans réponse (mais 2 ports ouverts entrevus) |
| Bruteforce SSH (15 connexions) | 15/15 répondues | 5/15 répondues |
| Flood ICMP (60 pings) | 0 % de pertes | environ 67 % de pertes |
| Injection SQL | HTTP 200 | aucune réponse (connexion coupée) |
| Trafic normal (ping, web, SSH) | 3/3 | 3/3 : **aucun faux positif** |

## 6. Les limites : le dire soi-même est un point fort

- **Détection par signatures** : on ne détecte que ce qu'on a décrit. Un attaquant lent ou une attaque inconnue passe. Piste d'amélioration : détection d'anomalies par machine learning.
- **Seuils** : l'IPS laisse passer les premiers paquets avant le seuil. Exemple vu en test : nmap sonde d'abord les ports courants (22, 80), donc il les *entrevoit* avant d'être coupé.
- **Une seule machine** : Snort et Suricata tournent sur la même machine que la cible. En vrai, on placerait l'IPS devant le réseau (en passerelle) et l'IDS sur un port miroir.
- **Pas de chiffrement** : le contenu HTTPS ne peut pas être lu par ces règles.
- **Lab, pas production** : le dashboard n'a pas d'authentification.

## 7. Questions probables du jury

**Pourquoi deux outils ?** Pour *voir* la différence entre détecter (Snort, IDS) et bloquer (Suricata, IPS) sur les mêmes attaques.

**Pourquoi un IPS peut-il être dangereux ?** Un faux positif coupe du trafic légitime. C'est pourquoi `attack.sh` commence par un contrôle de trafic normal.

**Où est l'intelligence ?** L'IA analyse chaque alerte comme un analyste SOC (explication, gravité, conseil). La détection elle-même reste à base de règles ; le machine learning est la suite logique du projet.

**À quoi sert la base SQL ?** À garder l'historique et à produire les statistiques (top attaquants, comparaison des sondes).

**Qu'as-tu fait toi-même ?** Montage du labo, règles, tests des attaques, analyse des résultats. *(Le projet a été développé avec l'aide d'une IA ; dis-le franchement, et sois capable d'expliquer chaque fichier grâce à ce guide.)*

## 8. Plan possible pour le rapport

1. Contexte et objectifs (IDS contre IPS) ; 2. Architecture du labo (schéma + captures VirtualBox) ;
3. Installation et configuration (Snort, Suricata, règles) ; 4. Scénarios d'attaque ; 5. Résultats (tableau + captures du dashboard + Telegram) ;
6. Analyse et limites ; 7. Perspectives (machine learning, placement réseau réaliste, plus de règles).
