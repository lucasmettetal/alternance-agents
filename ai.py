"""
Envoie une entreprise à Ollama et retourne un score d'attractivité alternance.
"""

import json
import re
from litellm import completion

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "ollama/llama3.2"

PROMPT_TEMPLATE = """Tu es un conseiller en orientation pour étudiants en BTS SIO.
Analyse cette entreprise et évalue sa probabilité d'accueillir un alternant en informatique
(support IT, helpdesk, technicien réseaux, administration systèmes, cybersécurité débutant).

Entreprise : {nom}
Activité NAF : {naf} – {activite}
Ville : {ville} ({code_postal})
Effectif : {effectif}

Réponds UNIQUEMENT en JSON valide, sans texte autour :
{{"score": <entier de 0 à 10>, "raison": "<une phrase courte>"}}

Score 0 = aucun lien avec l'IT / Score 10 = entreprise IT idéale pour alternance."""


def score_company(company: dict, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL) -> dict:
    """
    Retourne le dict company enrichi de 'score' (int) et 'raison' (str).
    En cas d'échec, score = -1 et raison = message d'erreur.
    """
    prompt = PROMPT_TEMPLATE.format(
        nom=company.get("nom", ""),
        naf=company.get("naf", ""),
        activite=company.get("activite", ""),
        ville=company.get("ville", ""),
        code_postal=company.get("code_postal", ""),
        effectif=company.get("effectif", "inconnu"),
    )

    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_base=base_url,
        )
        raw = response["choices"][0]["message"]["content"].strip()
        data = _parse_json(raw)
        company["score"] = int(data.get("score", -1))
        company["raison"] = data.get("raison", "")
    except Exception as e:
        company["score"] = -1
        company["raison"] = f"Erreur: {e}"

    return company


def _parse_json(text: str) -> dict:
    """Extrait le premier bloc JSON de la réponse même si Ollama ajoute du texte."""
    # Tentative directe
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Extraction par regex si le modèle ajoute du texte autour
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"Pas de JSON valide dans : {text[:200]}")
