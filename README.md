# alternance-agents

Outil local de prospection pour trouver des entreprises susceptibles de recruter en alternance informatique autour de **Caussade**, **Montauban** et **Toulouse**.

## Ce que ça fait

1. Cherche toutes les entreprises locales via l'[API Recherche Entreprises](https://recherche-entreprises.api.gouv.fr/) (recherche par code postal + mots-clés IT)
2. Score chaque entreprise : score déterministe + score Ollama (llama3.2 en local)
3. Enrichit les données : site officiel, LinkedIn, email, téléphone via DuckDuckGo + scraping
4. Compare chaque entreprise à ton profil CV extrait automatiquement
5. Exporte un CSV de prospection avec statuts, notes et recommandations
6. Interface Streamlit pour filtrer, éditer les statuts et générer des emails de candidature

---

## Stack

- Python 3.10+
- [Ollama](https://ollama.com/) + llama3.2 (scoring IA local, aucune clé API requise)
- [litellm](https://github.com/BerriAI/litellm) — interface unifiée Ollama
- [ddgs](https://pypi.org/project/ddgs/) — recherche DuckDuckGo
- [Streamlit](https://streamlit.io/) — interface web
- API gouvernementale gratuite : `recherche-entreprises.api.gouv.fr`

---

## Installation

```bash
# Cloner le repo
git clone https://github.com/lucasmettetal/alternance-agents.git
cd alternance-agents

# Créer l'environnement virtuel
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# Installer les dépendances
pip install litellm ddgs streamlit requests python-dotenv
```

Installer et démarrer Ollama :

```bash
# https://ollama.com/download
ollama pull llama3.2
ollama serve
```

---

## Configuration

Créer un fichier `.env` à la racine (non versionné) :

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=ollama/llama3.2
MAX_PER_CITY=50
OUTPUT_FILE=output/leads_alternance.csv
ENRICH=true
```

| Variable | Rôle |
|---|---|
| `MAX_PER_CITY` | Nombre max d'entreprises par ville (défaut : 50) |
| `ENRICH` | Active la recherche de contacts web (`true`/`false`) |

---

## Profil CV

Remplis le fichier `data/cv_lucas.txt` avec ton CV en texte brut (ce fichier est gitignore — il reste en local) :

```
== Formation ==
BTS SIO option SISR - Lycée X - 2024-2026

== Compétences techniques ==
Windows Server, Active Directory, Linux, TCP/IP, VLAN, VPN...

== Projets ==
...

== Objectif ==
Alternance systèmes/réseaux, évolution cybersécurité.
```

Au premier lancement, Ollama extrait un profil structuré et le met en cache dans `data/cv_profile_cache.json`. Le cache est regénéré automatiquement si tu modifies le CV.

---

## Utilisation

### Interface Streamlit (recommandée)

```bash
streamlit run app.py
```

- **Rechercher** : lance le pipeline complet (recherche + scoring + enrichissement)
- **Actualiser profil CV** : regénère le profil depuis ton CV mis à jour
- **Filtres** : ville, score, statut, action recommandée, intérêt
- **Tableau éditable** : modifie les statuts, dates, notes directement
- **Générer un message** : crée un email de candidature personnalisé via Ollama

### En ligne de commande

```bash
python main.py
```

---

## Colonnes du CSV exporté

| Colonne | Description |
|---|---|
| `score_final` | Score combiné (déterministe + IA), 0-100 |
| `zone_score` | Score géographique : 30=ville cible, 15=dept, négatif=hors zone |
| `cv_match_score` | Correspondance avec ton profil CV, 0-10 |
| `company_type` | Type détecté : ESN / infogérance / dépannage PC / cloud… |
| `mission_probable` | Ce qu'un alternant IT ferait probablement là-bas |
| `interet_pour_lucas` | élevé / moyen / faible |
| `risque` | Principal point de vigilance |
| `action_recommandee` | contacter maintenant / vérifier avant contact / garder en réserve / exclure |
| `contact_confidence` | Fiabilité des coordonnées : élevée / moyenne / faible |
| `site_type` | officiel / annuaire / à vérifier / absent |
| `statut_contact` | À remplir manuellement : contacté / relance / refus / entretien |

---

## Architecture

```
alternance-agents/
├── sources.py       # Recherche entreprises via API gouv (code postal + mots-clés)
├── scorer.py        # Score déterministe (NAF, zone, mots-clés, effectif, liquidation)
├── ai.py            # Score Ollama : adéquation alternance + matching profil CV
├── enricher.py      # Enrichissement web (site, LinkedIn, email, téléphone)
├── cv_profile.py    # Extraction profil structuré depuis cv_lucas.txt via Ollama
├── main.py          # Pipeline CLI + export CSV
├── app.py           # Interface Streamlit
├── data/            # (gitignore) — cv_lucas.txt, cv_profile_cache.json
├── output/          # (gitignore) — leads_alternance.csv
└── .env             # (gitignore) — configuration locale
```

### Logique de scoring

```
basic_score (0-100)
  = NAF IT (0-15)
  + zone géographique (-20 à +30)
  + mots-clés nom/activité (0-30)
  + effectif sweet spot (0-15)
  - malus liquidation (-60)
  - malus inactive/radiée (-50)

score_final = (basic_score + score_ia × 10) / 2

action_recommandee
  → exclure           : liquidation, hors zone, cv_match ≤ 3, intérêt faible
  → contacter maintenant  : score ≥ 55, confiance élevée/moyenne, cv_match ≥ 6
  → vérifier avant contact : score ≥ 40
  → garder en réserve : reste
```

---

## Villes couvertes

| Ville | Code postal | Rayon de recherche |
|---|---|---|
| Montauban | 82000 | Siège exact |
| Caussade | 82300 | Siège exact |
| Toulouse | 31000 | Siège exact (centre) |

Les entreprises avec siège hors zone (Île-de-France, Bordeaux…) sont automatiquement détectées et pénalisées via le `zone_score`.

---

## Notes

- Aucune donnée n'est envoyée à des serveurs externes : tout tourne en local (Ollama, API gouv gratuite, scraping).
- Les emails marqués `(estimé)` sont déduits du domaine du site — à vérifier avant d'envoyer.
- Le fichier CSV conserve tes notes et statuts lors d'un nouveau scan (merge par SIREN).
