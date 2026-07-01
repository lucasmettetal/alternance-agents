"""
Récupère des entreprises locales depuis l'API gouvernementale.
Stratégie : code postal + mots-clés IT (pas de filtre NAF obligatoire).
→ Capture toutes les entreprises de la ville susceptibles d'employer en IT,
  pas seulement celles dont l'activité principale est 100% informatique.
"""

import requests

API_URL = "https://recherche-entreprises.api.gouv.fr/search"

# Mots-clés envoyés à l'API : cherchent dans le nom ET la description de l'entreprise.
# On les couvre tous pour maximiser la couverture locale.
IT_KEYWORDS = [
    "informatique",
    "logiciel",
    "reseau",
    "numerique",
    "cyber",
    "telecom",
    "systemes",
    "digital",
    "cloud",
]

# Labels NAF pour affichage (non exhaustif — code brut affiché si absent)
NAF_LABELS = {
    "62.01Z": "Programmation informatique",
    "62.02A": "Conseil systèmes et logiciels",
    "62.02B": "Tierce maintenance",
    "62.03Z": "Gestion installations informatiques",
    "62.09Z": "Autres activités informatiques",
    "63.11Z": "Traitement de données, hébergement",
    "63.12Z": "Portails internet",
    "95.11Z": "Réparation ordinateurs",
    "95.12Z": "Réparation équipements télécom",
    "61.10Z": "Télécommunications filaires",
    "61.20Z": "Télécommunications mobiles",
    "61.90Z": "Autres télécommunications",
    "64.19Z": "Autres activités de services financiers",
    "84.11Z": "Administration publique générale",
    "86.10Z": "Activités hospitalières",
    "26.20Z": "Fabrication ordinateurs et équipements",
}

# Villes cibles : code postal pour filtrer précisément par ville
# (et non par département entier, qui ramènerait tout le 82 ou tout le 31)
CITIES = [
    {"name": "Montauban", "code_postal": "82000", "departement": "82"},
    {"name": "Caussade",  "code_postal": "82300", "departement": "82"},
    {"name": "Toulouse",  "code_postal": "31000", "departement": "31"},
]


_QUALITES_SKIP = {"commissaire aux comptes", "commissaire", "auditeur", "censeur"}


def _extract_dirigeant(dirigeants: list) -> str:
    """Retourne le premier décideur (personne physique, hors commissaires)."""
    for d in dirigeants:
        if d.get("type_dirigeant") != "personne physique":
            continue
        qualite = (d.get("qualite") or "").lower()
        if any(s in qualite for s in _QUALITES_SKIP):
            continue
        prenom = (d.get("prenoms") or "").split()[0]
        nom    = d.get("nom") or ""
        role   = d.get("qualite") or ""
        name   = " ".join(p for p in [prenom, nom] if p)
        return f"{name} ({role})" if role else name
    return ""


def _fetch_page(code_postal: str, keyword: str, page: int = 1, per_page: int = 25) -> dict:
    """Appel API unique. Retourne le JSON brut."""
    try:
        r = requests.get(
            API_URL,
            params={
                "code_postal": code_postal,
                "q":           keyword,
                "per_page":    per_page,
                "page":        page,
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [!] Erreur API (cp={code_postal}, q={keyword}, p={page}): {e}")
        return {}


def _build_company(r: dict, city: dict, keyword: str) -> dict:
    """Construit le dict entreprise depuis une entrée API."""
    siege = r.get("siege", {})
    naf   = r.get("activite_principale", "")
    return {
        "siren":             r.get("siren", ""),
        "siret":             siege.get("siret", ""),
        "nom":               r.get("nom_raison_sociale") or r.get("nom_complet") or "",
        "naf":               naf,
        "activite":          NAF_LABELS.get(naf, naf),
        "ville":             siege.get("libelle_commune") or city["name"],
        "code_postal":       siege.get("code_postal", city["code_postal"]),
        "etat_administratif": r.get("etat_administratif", "A"),
        "departement":       city["departement"],
        "dirigeant":         _extract_dirigeant(r.get("dirigeants", [])),
        "effectif":          r.get("tranche_effectif_salarie") or "",
        "nature_juridique":  r.get("nature_juridique") or "",
        "_keyword":          keyword,   # trace interne, non exporté
    }


def get_companies_for_city(city: dict, max_results: int = 50) -> list[dict]:
    """
    Collecte toutes les entreprises de la ville qui correspondent
    aux mots-clés IT, en paginant si nécessaire.
    Déduplique par SIREN.
    """
    seen_sirens: set[str] = set()
    companies: list[dict] = []
    per_page = 25

    for keyword in IT_KEYWORDS:
        if len(companies) >= max_results:
            break

        # Première page + total pour savoir si pagination nécessaire
        data  = _fetch_page(city["code_postal"], keyword, page=1, per_page=per_page)
        total = data.get("total_results", 0)
        pages = [data.get("results", [])]

        # Pages suivantes si besoin (et si le quota max n'est pas atteint)
        remaining = min(total - per_page, max_results - len(companies))
        page = 2
        while remaining > 0 and len(companies) < max_results:
            extra = _fetch_page(city["code_postal"], keyword, page=page, per_page=per_page)
            pages.append(extra.get("results", []))
            remaining -= per_page
            page += 1

        for raw_page in pages:
            for r in raw_page:
                siren = r.get("siren", "")
                if not siren or siren in seen_sirens:
                    continue
                seen_sirens.add(siren)
                companies.append(_build_company(r, city, keyword))
                if len(companies) >= max_results:
                    break

    return companies
