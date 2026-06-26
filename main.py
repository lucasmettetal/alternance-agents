"""
Point d'entrée : cherche des entreprises IT autour de Caussade, Montauban, Toulouse,
les score avec Ollama, et exporte un CSV dans output/leads_alternance.csv.
"""

import csv
import os
from dotenv import load_dotenv

from sources import CITIES, get_companies_for_city
from ai import score_company

load_dotenv()

MAX_PER_CITY = int(os.getenv("MAX_PER_CITY", 15))
OUTPUT_FILE  = os.getenv("OUTPUT_FILE", "output/leads_alternance.csv")

CSV_FIELDS = ["nom", "ville", "code_postal", "naf", "activite", "effectif", "score", "raison", "siren"]


def main():
    all_companies = []
    seen_sirens: set[str] = set()

    for city in CITIES:
        print(f"\n=== {city['name']} (dept. {city['departement']}) ===")
        companies = get_companies_for_city(city, max_results=MAX_PER_CITY)

        # Déduplique globalement (Caussade + Montauban -> même dept 82)
        new_companies = [c for c in companies if c["siren"] not in seen_sirens]
        seen_sirens.update(c["siren"] for c in new_companies)
        print(f"  {len(new_companies)} nouvelles entreprises ({len(companies) - len(new_companies)} doublons ignorés)")

        for i, company in enumerate(new_companies, 1):
            name_preview = (company["nom"] or "?")[:50]
            print(f"  [{i}/{len(new_companies)}] Scoring : {name_preview}", end=" ", flush=True)
            scored = score_company(company)
            print(f"-> {scored['score']}/10")
            all_companies.append(scored)

    # Tri par score décroissant
    all_companies.sort(key=lambda c: c.get("score", -1), reverse=True)

    # Export CSV
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_companies)

    print(f"\nOK {len(all_companies)} entreprises exportées -> {OUTPUT_FILE}")

    # Aperçu top 5
    print("\n--- Top 5 ---")
    for c in all_companies[:5]:
        print(f"  {c['score']:>2}/10  {c['nom'][:40]:<40}  {c['ville']}")


if __name__ == "__main__":
    main()
