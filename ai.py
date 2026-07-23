"""
Envoie une entreprise à Ollama et retourne un score d'attractivité alternance,
enrichi d'une analyse CV-match (profil Lucas vs entreprise).
"""

import json
import re
from litellm import completion
from cv_profile import get_profile, profile_summary

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = "ollama/llama3.2"

_PROMPT = """Tu es un assistant spécialisé dans la recherche d'alternance en développement web et infrastructure IT.
{profil_context}

Analyse cette entreprise et évalue son adéquation avec ce profil.

Entreprise : {nom}
Activité NAF : {naf} – {activite}
Ville : {ville} ({code_postal})
Effectif : {effectif}

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans texte autour) :
{{
  "score": 7,
  "raison": "justification courte de l'adéquation globale",
  "cv_match_score": 6,
  "cv_match_reason": "correspondance avec le profil : points forts et points faibles",
  "company_type": "ESN",
  "mission_probable": "ce qu'un alternant IT ferait probablement ici",
  "interet_pour_lucas": "élevé",
  "risque": "principal point de vigilance"
}}

Règles :
- score et cv_match_score sont des entiers 0-10
- company_type : ESN / infogérance / dépannage PC / cloud / hébergement / industrie / DSI / commerce / autre
- interet_pour_lucas : élevé / moyen / faible
- Dépannage PC particuliers ou réparation basique → cv_match_score bas (≤3), interet_pour_lucas=faible
- ESN, infogérance, DSI, cloud, réseaux → cv_match_score élevé si activité correspond au profil"""


def score_company(company: dict, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL) -> dict:
    """
    Enrichit le dict company avec :
    score, raison, cv_match_score, cv_match_reason,
    company_type, mission_probable, interet_pour_lucas, risque,
    json_valide, reponse_brute, erreur_parsing.
    """
    profile = get_profile()

    prompt = _PROMPT.format(
        profil_context=profile_summary(profile),
        nom=company.get("nom", ""),
        naf=company.get("naf", ""),
        activite=company.get("activite", ""),
        ville=company.get("ville", ""),
        code_postal=company.get("code_postal", ""),
        effectif=company.get("effectif", "inconnu"),
    )

    raw = ""
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_base=base_url,
        )
        raw = response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        company.update({
            "score": -1, "raison": "",
            "cv_match_score": -1, "cv_match_reason": "",
            "company_type": "", "mission_probable": "",
            "interet_pour_lucas": "", "risque": "",
            "json_valide": False, "reponse_brute": "",
            "erreur_parsing": f"Erreur Ollama : {e}",
        })
        return company

    data, erreur = _parse_json(raw)

    company.update({
        "score":              _safe_int(data.get("score", -1)),
        "raison":             data.get("raison", ""),
        "cv_match_score":     _safe_int(data.get("cv_match_score", -1)),
        "cv_match_reason":    data.get("cv_match_reason", ""),
        "company_type":       data.get("company_type", ""),
        "mission_probable":   data.get("mission_probable", ""),
        "interet_pour_lucas": data.get("interet_pour_lucas", ""),
        "risque":             data.get("risque", ""),
        "json_valide":        erreur is None,
        "reponse_brute":      raw,
        "erreur_parsing":     erreur or "",
    })
    return company


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return -1


def _parse_json(text: str) -> tuple[dict, str | None]:
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        pass

    stripped = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group()), None
        except json.JSONDecodeError as e:
            return {}, f"JSON malformé : {e} | extrait : {match.group()[:100]}"

    return {}, f"Aucun bloc JSON trouvé dans : {text[:200]}"
