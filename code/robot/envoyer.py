"""Mise en ligne automatique d'un épisode par l'API YouTube (videos.insert).

DÉSACTIVÉ tant que le projet Google n'a pas passé l'audit de conformité de YouTube :
sans audit, toute vidéo envoyée par l'API reste privée pour toujours.
Activation : variable AUDIT_ACCEPTE=oui (à ajouter seulement après la réponse de Google).

Usage : python robot/envoyer.py chemin/vers/ep05_xxx_FR.mp4
  1. envoi « reprenable » (resumable) de la vidéo, en PRIVÉ, avec titre, description,
     balises, langue, « conçue pour les enfants » et publication programmée à minuit ;
  2. sous-titres FR/EN/ES, miniature et titres EN/ES de la fiche du dépôt.
Ne publie jamais une vidéo immédiatement.
"""
import datetime as dt
import os
import pathlib
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fiches  # noqa: E402
import programmer as p  # noqa: E402

TAILLE_MORCEAU = 8 * 1024 * 1024


def prochain_minuit_libre(c, code):
    maintenant = dt.datetime.now(p.TZ)
    if code.startswith("jour"):
        return p.minuit(dt.date(maintenant.year, 12, int(code[4:])))
    occupes = set()
    for v in p.toutes_les_videos(c):
        st = v["status"]
        if st.get("publishAt"):
            occupes.add(p.date_locale(st["publishAt"]).date())
    jour = (maintenant + p.MARGE).date() + dt.timedelta(days=1)
    while jour in occupes:
        jour += dt.timedelta(days=1)
    return p.minuit(jour)


def envoyer(c, fichier, code, f, quand, categorie="27"):
    meta = {
        "snippet": p.snippet_de(f, categorie),
        "status": {"privacyStatus": "private", "publishAt": p.en_utc(quand),
                   "selfDeclaredMadeForKids": True, "containsSyntheticMedia": False,
                   "embeddable": True, "license": "youtube"},
        "localizations": p.localisations(f, {}),
    }
    taille = fichier.stat().st_size
    r = requests.post(f"{p.UPLOAD}/videos", params={"uploadType": "resumable", "part": "snippet,status,localizations"},
                      json=meta, headers={**c.h, "X-Upload-Content-Type": "video/mp4",
                                          "X-Upload-Content-Length": str(taille)}, timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"ERREUR au début de l'envoi ({r.status_code}) : {r.text[:300]}")
    adresse = r.headers["Location"]
    debut = 0
    with fichier.open("rb") as fh:
        while debut < taille:
            morceau = fh.read(TAILLE_MORCEAU)
            fin = debut + len(morceau) - 1
            r = requests.put(adresse, data=morceau, timeout=300,
                             headers={"Content-Range": f"bytes {debut}-{fin}/{taille}"})
            if r.status_code in (200, 201):
                return r.json()["id"]
            if r.status_code != 308:
                raise SystemExit(f"ERREUR pendant l'envoi ({r.status_code}) : {r.text[:300]}")
            plage = r.headers.get("Range")
            debut = int(plage.split("-")[1]) + 1 if plage else 0
            fh.seek(debut)
            print(f"  … {debut * 100 // taille} %", flush=True)
    raise SystemExit("ERREUR : envoi terminé sans identifiant de vidéo.")


def main():
    if os.environ.get("AUDIT_ACCEPTE", "").strip().lower() != "oui":
        raise SystemExit("Mise en ligne par l'API désactivée : en attente de l'audit de YouTube.")
    fichier = pathlib.Path(sys.argv[1])
    code = fiches.code_depuis_fichier(fichier.name)
    if not code:
        raise SystemExit(f"ERREUR : nom de fichier non reconnu ({fichier.name}).")
    f = fiches.lire_fiche(fiches.dossier_livraison(code))
    c = p.Client()
    quand = prochain_minuit_libre(c, code)
    vid = envoyer(c, fichier, code, f, quand)
    print(f"Vidéo envoyée en privé : https://youtu.be/{vid} — publication prévue {quand:%Y-%m-%d %H:%M}")
    for lg in fiches.LANGUES:
        if f["srt"][lg]:
            ok, msg = c.sous_titres(vid, lg, f["srt"][lg])
            print(f"  - sous-titres {lg.upper()} : {'✅' if ok else '❌ ' + msg}")
    if f["miniature"]:
        ok, msg = c.miniature(vid, f["miniature"])
        print(f"  - miniature : {'✅' if ok else '❌ ' + msg}")


if __name__ == "__main__":
    main()
