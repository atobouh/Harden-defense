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


class TelegramError(Exception):
    pass


def enabled():
    return bool(config.setting("TELEGRAM_BOT_TOKEN") and config.setting("TELEGRAM_CHAT_ID"))


def _api(method, params=None, timeout=10, token=None):
    token = token or config.setting("TELEGRAM_BOT_TOKEN")
    url = f"{config.setting('TELEGRAM_API_BASE').rstrip('/')}/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
        return json.load(r)


def _call(method, params=None, token=None):
    """Appel avec des messages d'erreur compréhensibles."""
    try:
        res = _api(method, params, token=token)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 404):
            raise TelegramError("Ce token n'est pas valide. Copie-le en entier depuis @BotFather, sans espace.")
        raise TelegramError(f"Telegram a refusé la demande (erreur {exc.code}).")
    except (urllib.error.URLError, OSError, ValueError):
        raise TelegramError("Impossible de joindre Telegram. Vérifie la connexion internet.")
    if not res.get("ok"):
        raise TelegramError(res.get("description") or "Telegram a refusé la demande.")
    return res["result"]


def get_me(token):
    """Vérifie un token : retourne le nom d'utilisateur du bot (sans @)."""
    return _call("getMe", token=token)["username"]


def find_chats(token):
    """Conversations qui ont écrit au bot (il faut lui avoir envoyé /start) : [{id, name}]."""
    found = {}
    for upd in _call("getUpdates", token=token):
        chat = (upd.get("message") or upd.get("channel_post") or {}).get("chat")
        if chat:
            found[chat["id"]] = chat.get("first_name") or chat.get("title") or chat.get("username") or str(chat["id"])
    return [{"id": cid, "name": name} for cid, name in found.items()]


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
    """Envoie un message. Retourne True si Telegram l'a accepté."""
    if not enabled():
        return False
    now = time.time()
    _sent[:] = [t for t in _sent if now - t < 60]
    if len(_sent) >= MAX_PER_MINUTE:
        print("[telegram] limite atteinte, message ignoré.", file=sys.stderr)
        return False
    try:
        res = _api("sendMessage", {"chat_id": config.setting("TELEGRAM_CHAT_ID"), "text": text,
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
    if not config.setting("TELEGRAM_BOT_TOKEN"):
        sys.exit("Aucun token Telegram : renseigne-le dans la page Réglages du dashboard (ou dans .env).")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "chatid":
        token = config.setting("TELEGRAM_BOT_TOKEN")
        print(f"Bot trouvé : @{get_me(token)}")
        chats = find_chats(token)
        if not chats:
            sys.exit("Aucun message reçu. Ouvre ton bot dans Telegram, envoie-lui « /start », puis relance cette commande.")
        for c in chats:
            print(f"TELEGRAM_CHAT_ID={c['id']}    ({c['name']})")
    elif cmd == "test":
        ok = send("✅ <b>Harden Defense</b> : le bot Telegram est bien relié.")
        print("Message envoyé !" if ok else "Échec : vérifie TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID.")
    else:
        sys.exit("Usage : python -m harden.telegram {chatid|test}")


if __name__ == "__main__":
    _cli()
