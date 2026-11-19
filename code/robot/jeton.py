"""Gestion des jetons YouTube du robot Lili & Pico.

Deux autorisations possibles :
- « complet » (client Application de bureau, portée youtube.force-ssl) :
  tout, y compris les sous-titres. Fichier jetons/youtube_complet.enc.
- « appareil » (client TV, portée youtube) : mise en ligne et métadonnées,
  pas les sous-titres. Fichier jetons/youtube.enc.

Chaque jeton de renouvellement est chiffré avec une clé dérivée du code secret
de son client (secret GitHub chiffré). Le fichier seul est inutilisable.
"""
import base64
import hashlib
import os
import pathlib

import requests
from cryptography.fernet import Fernet

DOSSIER = pathlib.Path(__file__).resolve().parent.parent / "jetons"
URL_JETON = "https://oauth2.googleapis.com/token"
PROFILS = {
    "complet": ("GOOGLE_DESKTOP_CLIENT_ID", "GOOGLE_DESKTOP_CLIENT_SECRET", "youtube_complet.enc"),
    "appareil": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "youtube.enc"),
}
FICHIER = DOSSIER / PROFILS["appareil"][2]  # compatibilité


def _identifiants(profil="appareil"):
    var_id, var_secret, _ = PROFILS[profil]
    cid = os.environ.get(var_id, "").strip()
    secret = os.environ.get(var_secret, "").strip()
    if not cid or not secret:
        raise SystemExit(f"ERREUR : {var_id} ou {var_secret} absent des secrets GitHub.")
    return cid, secret


def _fernet(secret):
    cle = hashlib.sha256(("robot-lili-pico:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(cle))


def masquer(valeur):
    """Demande à GitHub Actions de masquer cette valeur dans les journaux."""
    if valeur and os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{valeur}", flush=True)


def fichier(profil):
    return FICHIER if profil == "appareil" else DOSSIER / PROFILS[profil][2]


def enregistrer(refresh_token, profil="appareil"):
    _, secret = _identifiants(profil)
    f = fichier(profil)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(_fernet(secret).encrypt(refresh_token.encode()))


def profil_disponible():
    """Le meilleur profil utilisable : « complet » s'il existe, sinon « appareil »."""
    if fichier("complet").exists() and os.environ.get(PROFILS["complet"][1]):
        return "complet"
    return "appareil"


def jeton_acces(profil=None):
    """Renvoie un jeton d'accès valide (1 h) à partir du jeton chiffré."""
    profil = profil or profil_disponible()
    cid, secret = _identifiants(profil)
    f = fichier(profil)
    if not f.exists():
        raise SystemExit("ERREUR : aucun jeton. Lance d'abord le programme d'autorisation.")
    refresh = _fernet(secret).decrypt(f.read_bytes()).decode()
    masquer(refresh)
    r = requests.post(URL_JETON, data={
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        try:
            err = r.json().get("error", r.status_code)
        except ValueError:
            err = r.status_code
        if err == "invalid_grant":
            raise SystemExit("ERREUR : l'autorisation a expiré ou a été retirée. Relance le programme d'autorisation.")
        raise SystemExit(f"ERREUR lors du renouvellement du jeton : {err}")
    acces = r.json()["access_token"]
    masquer(acces)
    return acces
