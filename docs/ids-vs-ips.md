# IDS vs IPS : la différence en 2 minutes

| | **IDS** (Intrusion Detection System) | **IPS** (Intrusion Prevention System) |
|---|---|---|
| Rôle | Détecter et alerter | Détecter **et bloquer** |
| Place dans le réseau | À côté du trafic (il écoute une copie) | **Dans** le chemin du trafic (tout passe par lui) |
| Action sur une attaque | `alert` : prévient l'admin | `drop` : jette le paquet |
| Risque | L'attaque a déjà lieu pendant qu'on lit l'alerte | Un faux positif **coupe du trafic légitime** |
| Dans ce projet | **Snort** | **Suricata** (mode NFQUEUE) |

## Comment c'est fait ici

- **Snort** écoute l'interface réseau et écrit ses alertes dans `/var/log/snort/alert`. Il ne bloque jamais.
- **Suricata** a deux modes sur la même machine :
  - `lab.sh ids` : il écoute (af-packet), `drop` agit comme `alert`.
  - `lab.sh ips` : `iptables` envoie tous les paquets dans une file (`NFQUEUE`) que Suricata lit. S'il juge un paquet malveillant, il ne le renvoie pas : il est détruit avant d'atteindre Ubuntu.
- Les deux utilisent **les mêmes 4 attaques / 5 règles**, donc la comparaison est équitable.

## Ce qu'on démontre pendant le test

1. Mode IDS : Kali lance un scan nmap → les deux alertent, **le scan réussit** (Kali voit les ports).
2. Mode IPS : même scan → Snort alerte encore, mais **Suricata bloque** : Kali ne voit presque rien.

Phrase pour la soutenance : *« L'IDS me dit qu'on m'attaque, l'IPS empêche l'attaque. »*
