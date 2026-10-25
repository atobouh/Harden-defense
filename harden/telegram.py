"""Envoi des alertes sur Telegram (API officielle, sans bibliothèque externe)."""
import html
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, knowledge

ENGINE_LABEL = {"snort": "Snort (IDS)", "suricata": "Suricata (IPS)"}
_sent = []          # horodatages des derniers envois (limite anti-spam)
MAX_PER_MINUTE = 15


def enabled():
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _api(method, params=None, timeout=10):
    url = f"{config.TELEGRAM_API_BASE.rstrip('/')}/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
        return json.load(r)


def format_alert(alert, analysis):
    blocked = alert["action"] == "blocked"
    status = "⛔ <b>BLOQUÉE</b>" if blocked else "👁 <b>Détectée</b> (non bloquée)"
    name = knowledge.attack_name(alert["sid"], alert["signature"])
    dst = f"{alert['dst_ip']}:{alert['dst_port']}" if alert.get("dst_port") else alert["dst_ip"]
    lines = [
        f"🚨 <b>Harden Defense</b> — {html.escape(name)}",
        f"{status} par {ENGINE_LABEL.get(alert['engine'], alert['engine'])}",
        f"🎯 <code>{html.escape(str(alert['src_ip']))}</code> → <code>{html.escape(dst)}</code> ({html.escape(str(alert['proto']))})",
        "",
        f"🧠 <b>Analyse</b> (gravité {analysis['level']}/5)",
        html.escape(analysis["summary"]),
        f"✅ <i>{html.escape(analysis['advice'])}</i>",
    ]
    return "\n".join(lines)


def send(text):
    """Envoie un message. Retourne True si Telegram a accepté."""
    if not enabled():
        return False
    now = time.time()
    _sent[:] = [t for t in _sent if now - t < 60]
    if len(_sent) >= MAX_PER_MINUTE:
        print("[telegram] limite atteinte, message ignoré.", file=sys.stderr)
        return False
    try:
        res = _api("sendMessage", {"chat_id": config.TELEGRAM_CHAT_ID, "text": text,
                                   "parse_mode": "HTML", "disable_web_page_preview": "true"})
        _sent.append(now)
        return bool(res.get("ok"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"[telegram] échec d'envoi : {exc}", file=sys.stderr)
        return False


def notify(alert, analysis):
    return send(format_alert(alert, analysis))


# ---- petit outil en ligne de commande : python -m harden.telegram {chatid|test} ----
def _cli():
    if not config.TELEGRAM_BOT_TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN est vide : remplis le fichier .env d'abord.")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "chatid":
        me = _api("getMe")["result"]
        print(f"Bot trouvé : @{me['username']}")
        ids = {}
        for upd in _api("getUpdates").get("result", []):
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat")
            if chat:
                ids[chat["id"]] = chat.get("first_name") or chat.get("title") or ""
        if not ids:
            sys.exit("Aucun message reçu. Ouvre ton bot dans Telegram, envoie-lui « /start », puis relance cette commande.")
        for cid, name in ids.items():
            print(f"TELEGRAM_CHAT_ID={cid}    ({name})")
    elif cmd == "test":
        ok = send("✅ <b>Harden Defense</b> : le bot Telegram est bien relié.")
        print("Message envoyé !" if ok else "Échec : vérifie TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID.")
    else:
        sys.exit("Usage : python -m harden.telegram {chatid|test}")


if __name__ == "__main__":
    _cli()
