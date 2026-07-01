"""
Scoring déterministe d'une entreprise (avant le scoring IA).
Retourne un score 0-100 et une liste de raisons explicables.
"""

import re
import unicodedata

# --- Barème NAF ---
NAF_SCORES = {
    "62.01Z": 15,
    "62.02A": 15,
    "62.02B": 15,
    "62.03Z": 12,
    "62.09Z": 10,
    "63.11Z": 8,
    "95.11Z": 8,
    "95.12Z": 5,
    "63.12Z": 3,
}

# --- Géographie ---
# Villes cibles exactes
CITY_BONUS = {
    "caussade":  30,
    "montauban": 30,
    "toulouse":  25,
}
# Départements proches (zone principale et secondaire)
IN_ZONE_DEPTS   = {"31", "82"}
NEAR_ZONE_DEPTS = {"81", "46", "32", "12", "09"}

MALUS_OUTSIDE_ZONE = -20   # siège hors Occitanie/sud-ouest

# --- Mots-clés dans le nom ou l'activité ---
# "informatique" réduit à 7 pour éviter la surpondération des SSII génériques
KEYWORDS = {
    "informatique":     7,
    "logiciel":         8,
    "reseau":           8,
    "cloud":            7,
    "cybersecurite":   12,
    "cyber":            6,
    "maintenance":      5,
    "infogerance":      9,
    "telecom":          6,
    "telecommunication":6,
    "securite":         5,
    "support":          5,
    "helpdesk":         7,
    "systeme":          4,
    "hebergement":      5,
    "donnees":          4,
}
MAX_KEYWORD_PTS = 30

# --- Effectif (tranche INSEE) ---
EFFECTIF_SCORES = {
    "00": 0,   # 0 salarié
    "01": 2,   # 1-2
    "02": 3,   # 3-5
    "03": 5,   # 6-9
    "11": 10,  # 10-19
    "12": 15,  # 20-49  <- sweet spot
    "21": 12,  # 50-99
    "22": 10,  # 100-199
    "31": 8,   # 200-249
    "32": 6,   # 250-499
    "41": 4,   # 500-999
    "42": 3,   # 1000-1999
    "51": 2,
    "52": 2,
    "53": 2,
}

MALUS_INACTIVE    = -50   # etat_administratif == "F" (fermée) ou "R" (radiée)
MALUS_LIQUIDATION = -60   # liquidateur / liquidation judiciaire détecté

_LIQUIDATION_KW = {"liquidateur", "liquidation", "judiciaire", "dissolution"}


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _get_real_dept(company: dict) -> str:
    """Département déduit du code postal réel du siège, pas du champ 'departement' injecté."""
    cp = str(company.get("code_postal", "")).strip()
    return cp[:2] if len(cp) >= 2 else str(company.get("departement", ""))


def _zone_pts(company: dict) -> tuple[int, str]:
    """
    Calcule les points géographiques en fonction du vrai siège.
    Peut retourner une valeur négative (malus hors zone).
    """
    ville_norm = _normalize(company.get("ville", ""))
    dept = _get_real_dept(company)

    for city, bonus in CITY_BONUS.items():
        if city in ville_norm:
            return bonus, f"Ville cible {company.get('ville', '')} (+{bonus})"

    if dept in IN_ZONE_DEPTS:
        return 15, f"Departement {dept} (+15)"

    if dept in NEAR_ZONE_DEPTS:
        return 5, f"Departement proche {dept} (+5)"

    return MALUS_OUTSIDE_ZONE, f"Hors zone {company.get('ville', '')} ({MALUS_OUTSIDE_ZONE})"


def _is_liquidation(company: dict) -> bool:
    text = _normalize(" ".join(filter(None, [
        company.get("nom", ""),
        company.get("dirigeant", ""),
        company.get("activite", ""),
    ])))
    return any(kw in text for kw in _LIQUIDATION_KW)


def basic_score(company: dict) -> dict:
    """
    Calcule un score déterministe 0-100.
    Enrichit le dict avec : basic_score, basic_reasons, zone_score, _liquidation.
    """
    total = 0
    reasons: list[str] = []

    # 1. Code NAF (max 15)
    naf = company.get("naf", "")
    if naf in NAF_SCORES:
        pts = NAF_SCORES[naf]
        total += pts
        reasons.append(f"NAF {naf} (+{pts})")

    # 2. Géographie (basée sur le vrai siège, pas le département de recherche)
    zone_pts, zone_reason = _zone_pts(company)
    company["zone_score"] = zone_pts   # stocké pour export et action_recommandee
    total += zone_pts
    reasons.append(zone_reason)

    # 3. Mots-clés dans le nom et l'activité (max 30)
    searchable = _normalize(f"{company.get('nom', '')} {company.get('activite', '')}")
    kw_total = 0
    for kw, pts in KEYWORDS.items():
        if re.search(r"\b" + kw, searchable):
            kw_total += pts
            reasons.append(f'"{kw}" (+{pts})')
    kw_total = min(kw_total, MAX_KEYWORD_PTS)
    total += kw_total

    # 4. Effectif : sweet spot 20-99 salariés (max 15)
    effectif_code = str(company.get("effectif", "")).strip()
    eff_pts = EFFECTIF_SCORES.get(effectif_code, 0)
    if eff_pts:
        total += eff_pts
        reasons.append(f"Effectif {effectif_code} (+{eff_pts})")

    # 5. Entreprise inactive (fermée ou radiée)
    etat = company.get("etat_administratif", "A")
    if etat in ("F", "R"):
        total += MALUS_INACTIVE
        reasons.append(f"Entreprise inactive/radiee ({MALUS_INACTIVE})")

    # 6. Liquidation détectée dans le nom, l'activité ou le rôle du dirigeant
    liq = _is_liquidation(company)
    company["_liquidation"] = liq
    if liq:
        total += MALUS_LIQUIDATION
        reasons.append(f"Liquidation detectee ({MALUS_LIQUIDATION})")

    company["basic_score"]   = max(0, min(100, total))
    company["basic_reasons"] = " | ".join(reasons) if reasons else "aucun critere"
    return company
