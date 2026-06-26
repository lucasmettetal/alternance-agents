"""
Récupère des entreprises IT depuis l'API gouvernementale recherche-entreprises.
"""

import requests

API_URL = "https://recherche-entreprises.api.gouv.fr/search"

# Codes NAF (APE) liés à l'informatique et leurs libellés
NAF_IT = {
    "62.01Z": "Programmation informatique",
    "62.02A": "Conseil en systèmes et logiciels informatiques",
    "62.02B": "Tierce maintenance de systèmes et applications",
    "62.03Z": "Gestion d'installations informatiques",
    "62.09Z": "Autres activités informatiques",
    "63.11Z": "Traitement de données, hébergement",
    "63.12Z": "Portails internet",
    "95.11Z": "Réparation d'ordinateurs et périphériques",
    "95.12Z": "Réparation d'équipements de communication",
}

# Villes cibles avec leur département
CITIES = [
    {"name": "Caussade",   "departement": "82"},
    {"name": "Montauban",  "departement": "82"},
    {"name": "Toulouse",   "departement": "31"},
]


def fetch_companies_by_naf(departement: str, naf: str, per_page: int = 10) -> list[dict]:
    """Interroge l'API pour un code NAF + département."""
    try:
        resp = requests.get(
            API_URL,
            params={
                "activite_principale": naf,
                "departement": departement,
                "per_page": per_page,
                "page": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        print(f"  [!] Erreur API (dept={departement}, naf={naf}): {e}")
        return []


def get_companies_for_city(city: dict, max_results: int = 15) -> list[dict]:
    """Collecte des entreprises IT pour une ville donnée, dédupliquées par SIREN."""
    seen_sirens = set()
    companies = []

    for naf, label in NAF_IT.items():
        if len(companies) >= max_results:
            break
        raw = fetch_companies_by_naf(city["departement"], naf, per_page=5)
        for r in raw:
            siren = r.get("siren", "")
            if siren in seen_sirens:
                continue
            seen_sirens.add(siren)
            siege = r.get("siege", {})
            companies.append({
                "siren":    siren,
                "nom":      r.get("nom_raison_sociale") or r.get("nom_complet") or "",
                "naf":      naf,
                "activite": label,
                "ville":    siege.get("libelle_commune") or city["name"],
                "code_postal": siege.get("code_postal", ""),
                "adresse":  siege.get("adresse", ""),
                "effectif": r.get("tranche_effectif_salarie", ""),
            })

    return companies[:max_results]
