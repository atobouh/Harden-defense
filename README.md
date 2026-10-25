# Harden Defense

Mini-SOC pédagogique : on attaque une machine protégée et on compare un **IDS (Snort)** et un **IPS (Suricata)** face aux mêmes attaques.

```
 Kali Linux (attaquant)  ───────►  Ubuntu (défenseur)
                                    ├─ Snort     = IDS  (alerte)
                                    └─ Suricata  = IPS  (bloque)
```

Voir [docs/ids-vs-ips.md](docs/ids-vs-ips.md) pour la différence expliquée simplement.

## État du projet

- [x] Phase 1 : installation Snort + Suricata, mode IDS / IPS, règles communes
- [ ] Phase 2 : collecteur de logs, base SQLite, alertes Telegram
- [ ] Phase 3 : analyse de chaque alerte par une IA (clé API)
- [ ] Phase 4 : scripts d'attaque pour Kali + tableau comparatif
- [ ] Phase 5 : dashboard web + guide de soutenance

## Installation (VM Ubuntu)

Prérequis : deux VM VirtualBox, **sur le même réseau** (Réseau privé hôte, ou Réseau interne), chacune avec une IP. Vérifie avec `ip a` et un `ping` entre elles.

```bash
git clone https://github.com/atobouh/harden-defense.git
cd harden-defense
sudo ./scripts/install_defender.sh        # une seule fois (ajoute le nom de l'interface si besoin : enp0s8)
```

## Utilisation

```bash
sudo ./scripts/lab.sh ids      # mode détection : rien n'est bloqué
sudo ./scripts/lab.sh ips      # mode prévention : Suricata bloque
sudo ./scripts/lab.sh status
sudo ./scripts/lab.sh stop
```

Voir les alertes en direct :

```bash
sudo tail -f /var/log/snort/alert                                  # Snort
sudo tail -f /var/log/suricata/fast.log                            # Suricata
```

## Tester depuis Kali (remplace IP_UBUNTU)

```bash
nmap -sS -T4 IP_UBUNTU                                   # scan de ports
sudo hping3 --icmp --flood IP_UBUNTU                     # flood ICMP (Ctrl+C pour arrêter)
curl "http://IP_UBUNTU/?id=1' UNION SELECT 1,2--"        # injection SQL (il faut un serveur web sur Ubuntu : sudo apt install apache2)
```

## Les règles

- `config/snort/local.rules` : règles Snort (alert)
- `config/suricata/local.rules` : mêmes règles pour Suricata (drop)

Pour modifier une règle : édite le fichier puis relance `sudo ./scripts/install_defender.sh` et `sudo ./scripts/lab.sh ips`.

## Secrets

Le token Telegram et la clé API vont dans `.env` (copié depuis `.env.example`). Ce fichier est ignoré par git : ne le publie jamais.
