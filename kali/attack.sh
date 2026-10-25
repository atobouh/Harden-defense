#!/usr/bin/env bash
# À lancer depuis KALI.  Usage :  ./attack.sh IP_UBUNTU [legit|scan|ssh|icmp|sqli|all] [URL_DASHBOARD]
#   ex :  ./attack.sh 192.168.56.101 all http://192.168.56.101:5000
# Chaque attaque dit si elle est PASSÉE ou BLOQUÉE. Avec l'URL du dashboard, le résultat y est envoyé.
TARGET="${1:?Usage: $0 IP_UBUNTU [legit|scan|ssh|icmp|sqli|all] [URL_DASHBOARD]}"
WHAT="${2:-all}"
REPORT="${3:-}"

R=$'\e[31m'; G=$'\e[32m'; B=$'\e[1m'; D=$'\e[2m'; N=$'\e[0m'

report() {   # report SCENARIO PASSED(1/0) "détail"
  if [ "$2" = 1 ]; then echo "   → ${G}${B}ATTAQUE PASSÉE${N} (rien ne l'a arrêtée) — $3"
  else                  echo "   → ${R}${B}ATTAQUE BLOQUÉE${N} — $3"; fi
  if [ -n "$REPORT" ]; then      # en mode IPS on peut être bloqué un instant : on réessaie
    for _ in 1 2 3 4 5 6; do
      curl -sf -m 4 -X POST "$REPORT/api/attack_result" -H 'Content-Type: application/json' \
        -d "{\"scenario\":\"$1\",\"success\":$2,\"detail\":\"$3\"}" >/dev/null && break
      sleep 3
    done
  fi
  echo
}

legit() {
  echo "${B}[0/4] Contrôle : trafic normal${N} ${D}(ne doit JAMAIS être bloqué)${N}"
  ok=0; total=3
  ping -c 3 -i 0.5 -W 1 -q "$TARGET" >/dev/null 2>&1 && ok=$((ok+1))
  [ "$(curl -s -o /dev/null -m 4 -w '%{http_code}' "http://$TARGET/")" = 200 ] && ok=$((ok+1))
  timeout 2 bash -c "exec 3<>/dev/tcp/$TARGET/22" 2>/dev/null; [ $? -ne 124 ] && ok=$((ok+1))
  if [ "$ok" = "$total" ]; then echo "   → ${G}${B}OK${N} — ping, web et SSH normaux fonctionnent ($ok/$total)"
  else echo "   → ${R}${B}FAUX POSITIF${N} — du trafic légitime est bloqué ($ok/$total)"; fi
  echo
  sleep 6                          # laisse retomber les compteurs des règles
}

scan() {
  echo "${B}[1/4] Scan de ports${N} ${D}(nmap -sS, 500 ports)${N}"
  out="$(nmap -sS -Pn -T4 -p 1-500 --max-retries 1 --host-timeout 90s "$TARGET" 2>/dev/null)"
  if echo "$out" | grep -q 'are in state: filtered'; then filtered=500
  else filtered="$(echo "$out" | grep -o '[0-9]* filtered' | head -1 | grep -o '[0-9]*')"; fi
  filtered="${filtered:-0}"
  open="$(echo "$out" | grep -c '/tcp *open')"
  if [ "$filtered" -ge 250 ]; then
    report scan 0 "scan étouffé : $filtered/500 ports sans réponse, $open port(s) ouvert(s) entrevu(s)"
  else report scan 1 "$open port(s) ouvert(s) découvert(s), seulement $filtered/500 sans réponse"; fi
}

ssh_brute() {
  echo "${B}[2/4] Bruteforce SSH${N} ${D}(15 connexions rapides au port 22)${N}"
  answered=0
  for _ in $(seq 15); do
    timeout 2 bash -c "exec 3<>/dev/tcp/$TARGET/22" 2>/dev/null; rc=$?
    [ "$rc" -ne 124 ] && answered=$((answered+1))      # 124 = aucune réponse (paquet jeté)
  done
  if [ "$answered" -ge 12 ]; then report ssh 1 "$answered/15 connexions ont reçu une réponse"
  else report ssh 0 "seulement $answered/15 connexions ont reçu une réponse"; fi
}

icmp() {
  echo "${B}[3/4] Flood ICMP${N} ${D}(ping en rafale)${N}"
  iv=0.2; [ "$(id -u)" = 0 ] && iv=0.05
  loss="$(ping -c 60 -i "$iv" -W 1 -q "$TARGET" 2>/dev/null | grep -o '[0-9.]*% packet loss' | grep -o '^[0-9.]*')"
  loss="${loss:-100}"
  if [ "${loss%.*}" -lt 30 ]; then report icmp 1 "${loss}% de pertes seulement"
  else report icmp 0 "${loss}% des pings perdus"; fi
}

sqli() {
  echo "${B}[4/4] Injection SQL${N} ${D}(requête HTTP piégée)${N}"
  code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://$TARGET/?id=1%27%20UNION%20SELECT%201,2--")"
  if [ "$code" = 000 ]; then report sqli 0 "aucune réponse du serveur web (connexion coupée)"
  else report sqli 1 "le serveur a répondu HTTP $code"; fi
}

case "$WHAT" in
  scan) scan ;; ssh) ssh_brute ;; icmp) icmp ;; sqli) sqli ;;
  legit) legit ;;
  all)  legit; scan; ssh_brute; icmp; sqli ;;
  *) echo "Scénario inconnu : $WHAT (scan|ssh|icmp|sqli|all)"; exit 1 ;;
esac
