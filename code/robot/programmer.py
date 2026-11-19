"""Programme quotidien « Programmer les épisodes » du robot Lili & Pico.

Le propriétaire de la chaîne met en ligne le fichier mp4 en PRIVÉ (nom d'origine
conservé, ex. ep05_les_couleurs_FR.mp4 ou jour02_xxx_FR.mp4). Ce programme :
  1. repère la vidéo grâce au nom du fichier (fileDetails.fileName) ;
  2. ajoute les sous-titres FR/EN/ES, la miniature, le titre, la description,
     les balises et les traductions EN/ES de la fiche du dépôt ;
  3. en DERNIER, règle « conçue pour les enfants » et programme la publication :
     - épisode régulier : prochain minuit libre (heure de Montréal), 1 par jour ;
     - Avent « jourNN » : NN décembre à minuit.
  4. complète les vidéos déjà programmées s'il leur manque un sous-titre ou une traduction.

Sécurité : ne touche QUE les vidéos privées, sans date de publication, dont le
fichier correspond à un épisode du dépôt. Ne rend jamais une vidéo publique tout de
suite, ne supprime rien, ne modifie aucune vidéo publiée.
MODE=verifier (lecture seule, par défaut) | MODE=appliquer.

Note : mise en ligne par l'API (videos.insert) volontairement absente tant que le
projet Google n'a pas passé l'audit de YouTube (sinon la vidéo reste privée à vie).
"""
import datetime as dt
import json
import os
import sys
import uuid
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fiches  # noqa: E402
import jeton  # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
TZ = ZoneInfo("America/Toronto")  # même heure que Montréal
NOMS = {"fr": "Français", "en": "English", "es": "Español"}
VIDEO_REFERENCE = "a2SqxHbShTE"  # épisode 3 : on recopie sa catégorie
MAX_PAR_PASSAGE = 6  # quota : environ 1 300 unités par nouvel épisode (10 000 par jour)
MARGE = dt.timedelta(hours=3)  # minuit choisi au moins 3 h dans le futur
RAPPORT = []


def dire(texte=""):
    print(texte, flush=True)
    RAPPORT.append(texte)


class Client:
    def __init__(self):
        self.h = {"Authorization": f"Bearer {jeton.jeton_acces('complet')}"}

    def get(self, chemin, **params):
        r = requests.get(f"{API}/{chemin}", params=params, headers=self.h, timeout=60)
        if r.status_code != 200:
            raise SystemExit(f"ERREUR API {chemin} ({r.status_code}) : {r.text[:300]}")
        return r.json()

    def put(self, chemin, parts, corps):
        r = requests.put(f"{API}/{chemin}", params={"part": parts}, json=corps, headers=self.h, timeout=60)
        return r.status_code == 200, r.text[:300]

    def sous_titres(self, video_id, lg, fichier):
        meta = {"snippet": {"videoId": video_id, "language": lg, "name": NOMS[lg], "isDraft": False}}
        b = uuid.uuid4().hex
        corps = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                 f"--{b}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() \
            + fichier.read_bytes() + f"\r\n--{b}--\r\n".encode()
        r = requests.post(f"{UPLOAD}/captions", params={"part": "snippet", "uploadType": "multipart"}, data=corps,
                          headers={**self.h, "Content-Type": f"multipart/related; boundary={b}"}, timeout=120)
        return r.status_code == 200, r.text[:300]

    def miniature(self, video_id, fichier):
        r = requests.post(f"{UPLOAD}/thumbnails/set", params={"videoId": video_id}, data=fichier.read_bytes(),
                          headers={**self.h, "Content-Type": "image/png"}, timeout=120)
        return r.status_code == 200, r.text[:300]


def toutes_les_videos(c):
    ch = c.get("channels", part="contentDetails", mine="true")["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while True:
        p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if page:
            p["pageToken"] = page
        d = c.get("playlistItems", **p)
        ids += [it["contentDetails"]["videoId"] for it in d.get("items", [])]
        page = d.get("nextPageToken")
        if not page:
            break
    videos = []
    for i in range(0, len(ids), 50):
        videos += c.get("videos", part="snippet,status,fileDetails,localizations",
                        id=",".join(ids[i:i + 50])).get("items", [])
    return videos


def date_locale(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)


def minuit(jour):
    return dt.datetime.combine(jour, dt.time(0, 0), TZ)


def en_utc(moment):
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def langues_presentes(cles):
    return {lg for lg in ("fr", "en", "es") for k in cles if k.lower().startswith(lg)}


def completer(c, v, f, appliquer):
    """Sous-titres et traductions manquants. Renvoie le nombre d'erreurs."""
    erreurs = 0
    pistes = c.get("captions", part="snippet", videoId=v["id"]).get("items", [])
    deja = langues_presentes(p["snippet"]["language"] for p in pistes if p["snippet"].get("trackKind") != "asr")
    for lg in fiches.LANGUES:
        if lg in deja:
            continue
        if not f["srt"][lg]:
            dire(f"  - sous-titres {lg.upper()} : fichier absent du dépôt ❌")
            erreurs += 1
        elif appliquer:
            ok, msg = c.sous_titres(v["id"], lg, f["srt"][lg])
            dire(f"  - sous-titres {lg.upper()} : {'ajoutés ✅' if ok else '❌ ' + msg}")
            erreurs += not ok
        else:
            dire(f"  - sous-titres {lg.upper()} : à ajouter")
    loc = langues_presentes(v.get("localizations", {}))
    manque = [lg for lg in ("en", "es") if lg not in loc]
    if manque:
        dire(f"  - titres {'/'.join(m.upper() for m in manque)} : {'à ajouter' if not appliquer else 'ajout…'}")
    return erreurs, manque


def snippet_de(f, categorie):
    fr = f["infos"]["fr"]
    return {"title": fr["titre"][:100], "description": fr["description"][:5000], "tags": f["balises"],
            "categoryId": categorie, "defaultLanguage": "fr-CA", "defaultAudioLanguage": "fr-CA"}


def localisations(f, existantes):
    loc = dict(existantes or {})
    for lg in ("en", "es"):
        if f["infos"][lg]["titre"]:
            loc[lg] = {"title": f["infos"][lg]["titre"][:100], "description": f["infos"][lg]["description"][:5000]}
    return loc


def main():
    appliquer = os.environ.get("MODE", "verifier").strip() == "appliquer"
    c = Client()
    maintenant = dt.datetime.now(TZ)
    dire(f"# Programmer les épisodes — {'APPLIQUER' if appliquer else 'VÉRIFIER (lecture seule)'}")
    dire(f"Heure de Montréal : {maintenant:%Y-%m-%d %H:%M}")
    videos = toutes_les_videos(c)
    dire(f"Vidéos sur la chaîne : {len(videos)} ; noms de fichier lus : "
         + ", ".join(sorted(set(v.get("fileDetails", {}).get("fileName", "—") for v in videos))))
    ref = next((v for v in videos if v["id"] == VIDEO_REFERENCE), None)
    categorie = ref["snippet"].get("categoryId", "27") if ref else "27"

    # Jours déjà occupés par un épisode régulier (publié ou programmé)
    occupes = set()
    for v in videos:
        code = fiches.code_depuis_fichier(v.get("fileDetails", {}).get("fileName"))
        if code and code.startswith("jour"):
            continue
        st = v["status"]
        if st.get("publishAt"):
            occupes.add(date_locale(st["publishAt"]).date())
        elif st.get("privacyStatus") == "public":
            occupes.add(date_locale(v["snippet"]["publishedAt"]).date())

    a_programmer, programmees, ignorees = [], [], []
    for v in videos:
        nom = v.get("fileDetails", {}).get("fileName", "")
        code = fiches.code_depuis_fichier(nom)
        st = v["status"]
        if not code:
            if st.get("privacyStatus") == "private":
                ignorees.append(f"{v['id']} ({nom or 'nom de fichier inconnu'})")
            continue
        try:
            f = fiches.lire_fiche(fiches.dossier_livraison(code))
        except (StopIteration, FileNotFoundError):
            dire(f"\n⚠️ {code} ({v['id']}) : aucune fiche dans le dépôt. Rien n'est modifié.")
            continue
        if st.get("privacyStatus") == "private" and st.get("publishAt"):
            programmees.append((code, v, f))
        elif st.get("privacyStatus") == "private":
            a_programmer.append((code, v, f))

    erreurs = 0
    # 1) Vidéos déjà programmées : compléter ce qui manque
    for code, v, f in sorted(programmees, key=lambda x: x[1]["status"]["publishAt"]):
        quand = date_locale(v["status"]["publishAt"])
        dire(f"\n## {code} — déjà programmée : {quand:%Y-%m-%d %H:%M} — https://youtu.be/{v['id']}")
        e, manque = completer(c, v, f, appliquer)
        erreurs += e
        if manque and appliquer:
            ok, msg = c.put("videos", "localizations", {"id": v["id"], "localizations": localisations(f, v.get("localizations"))})
            dire(f"  - titres EN/ES : {'ajoutés ✅' if ok else '❌ ' + msg}")
            erreurs += not ok
        if not v["status"].get("madeForKids"):
            dire("  - ⚠️ pas indiquée « conçue pour les enfants » : à vérifier dans Studio (non modifié).")

    # 2) Nouvelles vidéos privées : tout appliquer puis programmer
    traitees = 0
    for code, v, f in sorted(a_programmer, key=lambda x: x[0]):
        dire(f"\n## {code} — nouvelle vidéo privée — https://youtu.be/{v['id']}")
        if v["status"].get("uploadStatus") != "processed":
            dire("  - encore en traitement chez YouTube : on réessaiera au prochain passage.")
            continue
        if traitees >= MAX_PAR_PASSAGE:
            dire("  - limite de quota du passage atteinte : au prochain passage.")
            continue
        if code.startswith("jour"):
            quand = minuit(dt.date(maintenant.year, 12, int(code[4:])))
            if quand - maintenant < MARGE:
                dire(f"  - ❌ date de l'Avent dépassée ({quand:%Y-%m-%d}) : rien n'est programmé.")
                erreurs += 1
                continue
        else:
            jour = (maintenant + MARGE).date() + dt.timedelta(days=1)
            while jour in occupes:
                jour += dt.timedelta(days=1)
            quand = minuit(jour)
        dire(f"  - publication prévue : {quand:%A %Y-%m-%d} à 0 h 00 (Montréal)")
        if not appliquer:
            completer(c, v, f, False)
            dire(f"  - titre FR, description, balises, miniature, « enfants » : à appliquer")
            if not code.startswith("jour"):
                occupes.add(quand.date())
            continue
        traitees += 1
        e, _ = completer(c, v, f, True)
        ok_min, msg = c.miniature(v["id"], f["miniature"]) if f["miniature"] else (False, "miniature absente du dépôt")
        dire(f"  - miniature : {'✅' if ok_min else '❌ ' + msg}")
        ok_sn, msg = c.put("videos", "snippet,localizations", {
            "id": v["id"], "snippet": snippet_de(f, categorie), "localizations": localisations(f, v.get("localizations"))})
        dire(f"  - titre, description, balises, titres EN/ES : {'✅' if ok_sn else '❌ ' + msg}")
        if e or not ok_min or not ok_sn:
            erreurs += e + (not ok_min) + (not ok_sn)
            dire("  - ⏸️ publication NON programmée à cause de l'erreur ci-dessus (nouvel essai au prochain passage).")
            continue
        st = v["status"]
        statut = {k: st[k] for k in ("embeddable", "license", "publicStatsViewable") if k in st}
        statut.update({"privacyStatus": "private", "publishAt": en_utc(quand),
                       "selfDeclaredMadeForKids": True, "containsSyntheticMedia": False})
        ok, msg = c.put("videos", "status", {"id": v["id"], "status": statut})
        dire(f"  - « conçue pour les enfants » + publication programmée : {'✅' if ok else '❌ ' + msg}")
        erreurs += not ok
        if ok and not code.startswith("jour"):
            occupes.add(quand.date())

    if ignorees:
        dire("\n## Vidéos privées non reconnues (laissées telles quelles)")
        for t in ignorees:
            dire(f"- {t}")

    # Réserve d'épisodes réguliers
    a_venir = sorted(d for d in occupes if d > maintenant.date())
    dire(f"\n## Réserve : {len(a_venir)} épisode(s) régulier(s) programmé(s)"
         + (f", jusqu'au {a_venir[-1]:%Y-%m-%d}" if a_venir else ""))
    demain = maintenant.date() + dt.timedelta(days=1)
    if demain not in occupes and maintenant.hour >= 12:
        dire(f"⚠️ Aucun épisode régulier prévu pour demain ({demain:%Y-%m-%d}) : mets une vidéo en ligne en privé.")

    chemin = os.environ.get("GITHUB_STEP_SUMMARY")
    if chemin:
        with open(chemin, "a", encoding="utf-8") as fh:
            fh.write("\n".join(RAPPORT) + "\n")
    dire(f"\nTERMINÉ — {erreurs} erreur(s).")
    sys.exit(1 if erreurs else 0)


if __name__ == "__main__":
    main()
