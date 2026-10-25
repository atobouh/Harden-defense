"""Les 4 attaques du projet : nom, explication et conseil (utilisés si l'IA n'est pas disponible)."""

# sid de la règle -> attaque
ATTACKS = {
    1000001: "scan",
    1000002: "ssh",
    1000003: "icmp",
    1000004: "sqli",
    1000005: "sqli",
}

NAMES = {
    "scan": "Scan de ports",
    "ssh": "Bruteforce SSH",
    "icmp": "Flood ICMP",
    "sqli": "Injection SQL",
}

LOCAL_ANALYSIS = {
    "scan": (
        "Quelqu'un teste un grand nombre de ports pour découvrir quels services tournent sur la machine. "
        "C'est la phase de reconnaissance qui précède une vraie attaque.",
        "Bloquer l'adresse source et fermer les ports inutiles.", 2),
    "ssh": (
        "Des connexions SSH se répètent très vite : un robot essaie de deviner un mot de passe.",
        "Bloquer l'IP, passer à l'authentification par clé et interdire la connexion root par mot de passe.", 4),
    "icmp": (
        "Un flot de pings sature la machine pour la ralentir ou la rendre indisponible (déni de service).",
        "Limiter l'ICMP avec le pare-feu et bloquer la source.", 3),
    "sqli": (
        "Une requête web contient du code SQL (UNION SELECT, OR 1=1) pour lire ou modifier la base de données du site.",
        "Bloquer l'IP, utiliser des requêtes préparées et ajouter un pare-feu applicatif (WAF).", 5),
}

GENERIC = ("Une règle de sécurité a été déclenchée par ce trafic.",
           "Vérifier la source de l'alerte dans les journaux.", 2)


def attack_key(sid):
    return ATTACKS.get(sid)


def attack_name(sid, signature=""):
    return NAMES.get(ATTACKS.get(sid), signature)


def local_analysis(sid):
    summary, advice, level = LOCAL_ANALYSIS.get(ATTACKS.get(sid), GENERIC)
    return {"summary": summary, "advice": advice, "level": level, "source": "local"}
