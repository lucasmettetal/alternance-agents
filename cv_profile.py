"""
Extrait un profil structuré depuis data/cv_lucas.txt via Ollama.
Mis en cache dans data/cv_profile_cache.json — régénéré si le CV est plus récent.
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from litellm import completion

load_dotenv()

CV_PATH    = Path("data/cv_lucas.txt")
CACHE_PATH = Path("data/cv_profile_cache.json")

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "ollama/llama3.2")
OLLAMA_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Profil par défaut utilisé si le CV est vide ou si Ollama échoue
DEFAULT_PROFILE = {
    "profil_cible": [
        "technicien systèmes et réseaux",
        "support informatique",
        "administrateur systèmes junior",
        "technicien helpdesk",
    ],
    "competences": ["Windows Server", "Linux", "Active Directory", "TCP/IP", "réseaux"],
    "projets_importants": [],
    "types_entreprises_a_cibler": [
        "ESN", "infogérance", "DSI interne", "hébergement", "cloud", "support pro",
    ],
    "types_entreprises_a_eviter": [
        "dépannage PC particuliers", "réparation smartphone", "commerce informatique",
    ],
    "mots_cles_positifs": [
        "infrastructure", "systèmes", "réseaux", "cloud", "cybersécurité",
        "support pro", "helpdesk", "infogérance",
    ],
    "mots_cles_negatifs": [
        "particuliers", "réparation", "dépannage domicile", "commerce", "vente",
    ],
    "pitch_court": (
        "BTS SIO SISR, cherche alternance systèmes/réseaux "
        "avec évolution progressive vers la cybersécurité"
    ),
}

_profile_cache: dict | None = None


def load_cv_text() -> str:
    if not CV_PATH.exists():
        return ""
    text = CV_PATH.read_text(encoding="utf-8").strip()
    # Fichier non rempli = contient encore les lignes entre crochets
    if text.startswith("[Remplace") or len(text) < 100:
        return ""
    return text


def extract_profile(cv_text: str) -> dict:
    """Appelle Ollama pour extraire le profil structuré depuis le texte du CV."""
    prompt = f"""Tu es un expert recrutement IT. Analyse ce CV et extrais un profil structuré.

CV :
{cv_text[:3000]}

Retourne UNIQUEMENT ce JSON (sans markdown, sans texte autour) :
{{
  "profil_cible": ["intitulés de postes recherchés"],
  "competences": ["compétences techniques"],
  "projets_importants": ["projets ou réalisations notables"],
  "types_entreprises_a_cibler": ["types d'entreprises adaptées"],
  "types_entreprises_a_eviter": ["types à éviter"],
  "mots_cles_positifs": ["mots-clés favorables dans une offre"],
  "mots_cles_negatifs": ["mots-clés défavorables"],
  "pitch_court": "résumé du profil en une phrase"
}}"""

    try:
        resp = completion(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            api_base=OLLAMA_URL,
        )
        text = resp["choices"][0]["message"]["content"].strip()

        for attempt in [
            lambda t: json.loads(t),
            lambda t: json.loads(re.sub(r"```(?:json)?\s*|\s*```", "", t).strip()),
            lambda t: json.loads(re.search(r"\{.*\}", t, re.DOTALL).group()),
        ]:
            try:
                parsed = attempt(text)
                return {**DEFAULT_PROFILE, **parsed}
            except Exception:
                continue

    except Exception as e:
        print(f"  [cv_profile] Erreur Ollama : {e}")

    return DEFAULT_PROFILE.copy()


def get_profile(force_refresh: bool = False) -> dict:
    """
    Retourne le profil structuré du candidat.
    Utilise le cache disque si le CV n'a pas changé depuis la dernière extraction.
    """
    global _profile_cache

    if _profile_cache and not force_refresh:
        return _profile_cache

    cv_mtime    = CV_PATH.stat().st_mtime    if CV_PATH.exists()    else 0
    cache_mtime = CACHE_PATH.stat().st_mtime if CACHE_PATH.exists() else 0

    if not force_refresh and cache_mtime > cv_mtime and CACHE_PATH.exists():
        try:
            _profile_cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            return _profile_cache
        except Exception:
            pass

    cv_text = load_cv_text()
    if not cv_text:
        _profile_cache = DEFAULT_PROFILE.copy()
        return _profile_cache

    print("  [cv_profile] Extraction du profil depuis le CV (une seule fois)...")
    _profile_cache = extract_profile(cv_text)

    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(_profile_cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  [cv_profile] Profil mis en cache -> {CACHE_PATH}")

    return _profile_cache


def profile_summary(profile: dict) -> str:
    """Résumé court du profil, injecté dans le prompt Ollama."""
    return (
        f"Profil : {profile.get('pitch_court', '')}\n"
        f"Postes cibles : {', '.join(profile.get('profil_cible', [])[:4])}\n"
        f"À cibler : {', '.join(profile.get('types_entreprises_a_cibler', [])[:4])}\n"
        f"À éviter : {', '.join(profile.get('types_entreprises_a_eviter', [])[:3])}"
    )
