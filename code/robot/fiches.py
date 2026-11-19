"""Lecture des fiches d'épisode (titres, descriptions, balises) et des fichiers livrés.

Une fiche « ..._titres_descriptions.txt » contient des sections FRANÇAIS / ENGLISH /
ESPAÑOL / RÉGLAGES séparées par des lignes de tirets. Fonctionne pour les épisodes
réguliers (episodes/epXX/livraison) et pour l'Avent (avent/jourXX/livraison).
"""
import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parent.parent
LANGUES = ["fr", "en", "es"]


def dossier_livraison(code):
    """« ep05 » → episodes/ep05/livraison ; « jour02 » → avent/jour02/livraison."""
    if code.startswith("ep"):
        return RACINE / "episodes" / code / "livraison"
    if code.startswith("jour"):
        return RACINE / "avent" / code / "livraison"
    raise ValueError(code)


def code_depuis_fichier(nom):
    """Nom du fichier mis en ligne → code d'épisode, ou None.

    ep05_xxx_FR.mp4 → ep05 ; jour02_xxx_FR.mp4 → jour02 (ep01 vit dans episode01/, ignoré).
    """
    nom = (nom or "").lower()
    m = re.match(r"(ep\d{2}|jour\d{2})(?=[_\-. ])", nom)
    if not m or m.group(1) == "ep01":
        return None
    return m.group(1)


def lire_fiche(dossier):
    fiche = next(dossier.glob("*titres_descriptions.txt"))
    texte = fiche.read_text(encoding="utf-8")
    sections = re.split(r"\n-{10,}\n(FRANÇAIS[^\n]*|ENGLISH[^\n]*|ESPAÑOL[^\n]*|RÉGLAGES[^\n]*)\n-{10,}\n", texte)
    blocs = {}
    for i in range(1, len(sections) - 1, 2):
        blocs[sections[i].split()[0]] = sections[i + 1]

    def champ(bloc, etiquettes, suivantes):
        motif = r"(?:%s)\s*:\s*\n(.*?)(?=\n(?:%s)\s*:\s*\n|\Z)" % ("|".join(etiquettes), "|".join(suivantes))
        m = re.search(motif, bloc, re.S)
        return m.group(1).strip() if m else ""

    fiches = {
        "fr": (blocs.get("FRANÇAIS", ""), ["Titre"], ["Description"], ["Balises"]),
        "en": (blocs.get("ENGLISH", ""), ["Title"], ["Description"], ["Tags"]),
        "es": (blocs.get("ESPAÑOL", ""), ["Título"], ["Descripción"], ["Etiquetas"]),
    }
    infos = {}
    for lg, (bloc, et_t, et_d, et_fin) in fiches.items():
        infos[lg] = {"titre": champ(bloc, et_t, et_d), "description": champ(bloc, et_d, et_fin)}
    m = re.search(r"Balises\s*:\s*\n(.*?)(?:\n\s*\n|\Z)", blocs.get("FRANÇAIS", ""), re.S)
    balises = [b.strip() for b in m.group(1).split(",") if b.strip()] if m else []
    srt = {lg: next(iter(sorted(dossier.glob(f"*sous-titres.{lg}.srt"))), None) for lg in LANGUES}
    miniature = next(iter(sorted(dossier.glob("miniature*.png"))), None)
    return {"infos": infos, "balises": balises, "srt": srt, "miniature": miniature}
