"""
Point d'entrée : cherche des entreprises IT autour de Caussade, Montauban, Toulouse,
les score avec Ollama, et exporte un CSV dans output/leads_alternance.csv.
"""

import csv
import os
from dotenv import load_dotenv

from sources import CITIES, get_companies_for_city
from scorer import basic_score
from ai import score_company
from enricher import enrich_company, compute_contact_confidence
from cv_profile import get_profile  # charge le profil au démarrage (mis en cache)

load_dotenv()

MAX_PER_CITY = int(os.getenv("MAX_PER_CITY", 15))
OUTPUT_FILE  = os.getenv("OUTPUT_FILE", "output/leads_alternance.csv")
ENRICH       = os.getenv("ENRICH", "false").lower() == "true"

CSV_FIELDS = [
    "nom", "ville", "code_postal", "siren", "siret",
    "code_naf", "activite", "dirigeant",
    "basic_score", "zone_score", "score_ia", "score_final", "raison_ia",
    "cv_match_score", "cv_match_reason",
    "company_type", "mission_probable", "interet_pour_lucas", "risque",
    "action_recommandee",
    "site_web", "site_type", "linkedin", "email", "contact_confidence", "telephone", "page_contact",
    "statut_contact", "date_contact", "relance", "notes",
]


def _compute_action(company: dict) -> str:
    etat         = company.get("etat_administratif", "A")
    is_liq       = company.get("_liquidation", False)
    zone         = company.get("zone_score", 0)
    score        = company.get("score_final", 0)
    confidence   = company.get("contact_confidence", "faible")
    cv_match     = company.get("cv_match_score", -1)
    company_type = (company.get("company_type") or "").lower()
    interet      = (company.get("interet_pour_lucas") or "").lower()

    # Exclusions absolues
    if is_liq or etat in ("F", "R"):
        return "exclure"
    if isinstance(zone, (int, float)) and zone < 0:
        return "exclure"

    # Entreprise hors profil selon l'IA
    if interet == "faible":
        return "garder en réserve"
    if cv_match >= 0 and cv_match <= 3:
        return "garder en réserve"

    # Dépannage PC particuliers → réserver sauf si score très élevé
    if any(kw in company_type for kw in ("dépannage pc", "réparation", "dépannage")):
        if score < 55:
            return "garder en réserve"

    # Contacts insuffisants pour contacter directement
    if confidence == "faible" and score < 55:
        return "vérifier avant contact"

    # Décision principale basée sur score + cv_match
    cv_ok = cv_match < 0 or cv_match >= 6   # cv_match -1 = pas encore calculé
    if score >= 55 and confidence in ("élevée", "moyenne") and cv_ok:
        return "contacter maintenant"
    if score >= 40 or (score >= 30 and cv_ok):
        return "vérifier avant contact"
    if score >= 20:
        return "garder en réserve"
    return "exclure"


def prepare_row(company: dict) -> dict:
    """Construit la ligne CSV finale depuis le dict interne."""
    score_ia    = company.get("score", -1)
    basic       = company.get("basic_score", 0)
    score_final = round((basic + score_ia * 10) / 2) if score_ia >= 0 else basic

    # Recalcule confidence si enrichissement non fait (run sans ENRICH)
    if "contact_confidence" not in company:
        company["contact_confidence"] = compute_contact_confidence(company)

    company["score_final"] = score_final   # stocké pour _compute_action

    return {
        "nom":                company.get("nom", ""),
        "ville":              company.get("ville", ""),
        "code_postal":        company.get("code_postal", ""),
        "siren":              company.get("siren", ""),
        "siret":              company.get("siret", ""),
        "code_naf":           company.get("naf", ""),
        "activite":           company.get("activite", ""),
        "dirigeant":          company.get("dirigeant", ""),
        "basic_score":        basic,
        "zone_score":         company.get("zone_score", 0),
        "score_ia":           score_ia,
        "score_final":        score_final,
        "raison_ia":          company.get("raison", ""),
        "cv_match_score":     company.get("cv_match_score", -1),
        "cv_match_reason":    company.get("cv_match_reason", ""),
        "company_type":       company.get("company_type", ""),
        "mission_probable":   company.get("mission_probable", ""),
        "interet_pour_lucas": company.get("interet_pour_lucas", ""),
        "risque":             company.get("risque", ""),
        "action_recommandee": _compute_action(company),
        "site_web":           company.get("site_web", ""),
        "site_type":          company.get("site_type", ""),
        "linkedin":           company.get("linkedin", ""),
        "email":              company.get("email", ""),
        "contact_confidence": company.get("contact_confidence", ""),
        "telephone":          company.get("telephone", ""),
        "page_contact":       company.get("page_contact", ""),
        "statut_contact":     "",
        "date_contact":       "",
        "relance":            "",
        "notes":              "",
    }


def main():
    all_companies = []
    seen_sirens: set[str] = set()

    for city in CITIES:
        print(f"\n=== {city['name']} (dept. {city['departement']}) ===")
        companies = get_companies_for_city(city, max_results=MAX_PER_CITY)

        new_companies = [c for c in companies if c["siren"] not in seen_sirens]
        seen_sirens.update(c["siren"] for c in new_companies)
        print(f"  {len(new_companies)} nouvelles entreprises ({len(companies) - len(new_companies)} doublons ignorés)")

        for i, company in enumerate(new_companies, 1):
            name_preview = (company["nom"] or "?")[:50]
            print(f"  [{i}/{len(new_companies)}] {name_preview}", end=" ", flush=True)
            basic_score(company)
            score_company(company)
            if ENRICH:
                enrich_company(company)
            status = "OK" if company["json_valide"] else "[!]"
            print(f"basic={company['basic_score']:>3}/100  ia={company['score']:>2}/10  zone={company.get('zone_score', '?'):>3}  {status}")
            all_companies.append(company)

    rows = [prepare_row(c) for c in all_companies]
    rows.sort(key=lambda r: r["score_final"], reverse=True)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nOK {len(rows)} entreprises exportées -> {OUTPUT_FILE}")

    print("\n--- Top 5 ---")
    for r in rows[:5]:
        print(f"  final={r['score_final']:>3}/100  ia={r['score_ia']:>2}/10  {r['nom'][:40]:<40}  {r['ville']}")


if __name__ == "__main__":
    main()
