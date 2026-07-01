"""
Interface Streamlit pour la prospection alternance informatique.
Usage : streamlit run app.py
"""

import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

OUTPUT_FILE   = os.getenv("OUTPUT_FILE", "output/leads_alternance.csv")
MAX_PER_CITY  = int(os.getenv("MAX_PER_CITY", 15))
ENRICH_DEFAULT = os.getenv("ENRICH", "false").lower() == "true"

STATUTS  = ["", "à contacter", "contacté", "relance", "refus", "entretien"]
ACTIONS  = ["contacter maintenant", "vérifier avant contact", "garder en réserve", "exclure"]
# Colonnes saisies manuellement à préserver lors d'un re-scan
USER_COLS = ["statut_contact", "date_contact", "relance", "notes"]
# Colonnes affichées dans le tableau
DISPLAY_COLS = [
    "nom", "ville", "score_final", "zone_score", "cv_match_score",
    "action_recommandee", "company_type", "interet_pour_lucas", "statut_contact",
    "dirigeant", "site_web", "site_type", "linkedin",
    "email", "contact_confidence", "telephone",
    "mission_probable", "risque", "cv_match_reason", "raison_ia",
    "notes", "date_contact",
]


# ── I/O ──────────────────────────────────────────────────────────────────────

def load_csv() -> pd.DataFrame:
    if not os.path.exists(OUTPUT_FILE):
        return pd.DataFrame()
    df = pd.read_csv(OUTPUT_FILE, encoding="utf-8-sig", dtype=str).fillna("")
    for col in ["basic_score", "score_ia", "score_final"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


def save_csv(df: pd.DataFrame):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")


def merge_and_save(edited: pd.DataFrame, df_full: pd.DataFrame):
    """Fusionne les lignes éditées (vue filtrée) dans le CSV complet."""
    full = df_full.set_index("siren").copy()
    edited_idx = edited.set_index("siren")
    full.update(edited_idx)
    save_csv(full.reset_index())


# ── Pipeline ─────────────────────────────────────────────────────────────────

def run_pipeline(enrich: bool = False):
    from sources import CITIES, get_companies_for_city
    from scorer import basic_score as bs
    from ai import score_company
    from enricher import enrich_company
    from main import prepare_row

    # Préserve les données utilisateur existantes
    old_data: dict[str, dict] = {}
    df_old = load_csv()
    if not df_old.empty and "siren" in df_old.columns:
        for _, row in df_old.iterrows():
            old_data[str(row["siren"])] = {c: row.get(c, "") for c in USER_COLS}

    companies, seen = [], set()
    total = len(CITIES) * MAX_PER_CITY
    bar = st.progress(0, "Initialisation…")

    for ci, city in enumerate(CITIES):
        batch = get_companies_for_city(city, max_results=MAX_PER_CITY)
        new   = [c for c in batch if c["siren"] not in seen]
        seen.update(c["siren"] for c in new)

        for i, company in enumerate(new):
            pct = min((ci * MAX_PER_CITY + i) / total, 0.97)
            bar.progress(pct, f"{city['name']} — {(company['nom'] or '')[:35]}")
            bs(company)
            score_company(company)
            if enrich:
                enrich_company(company)
            companies.append(company)

    rows = [prepare_row(c) for c in companies]

    # Réinjecte les données utilisateur
    for row in rows:
        siren = str(row.get("siren", ""))
        if siren in old_data:
            for col in USER_COLS:
                row[col] = old_data[siren].get(col, "")

    rows.sort(key=lambda r: r["score_final"], reverse=True)
    df_new = pd.DataFrame(rows)
    save_csv(df_new)
    bar.progress(1.0, "Terminé !")
    st.session_state["df_full"] = df_new


# ── Message ───────────────────────────────────────────────────────────────────

def generate_message(company: dict) -> str:
    from litellm import completion

    dirigeant = str(company.get("dirigeant", ""))
    prenom_nom = dirigeant.split("(")[0].strip()
    destinataire = f"M./Mme {prenom_nom}" if prenom_nom else "Madame, Monsieur"

    prompt = f"""Rédige un email de candidature spontanée pour une alternance informatique (BTS SIO).

Destinataire : {destinataire}
Entreprise   : {company.get("nom", "")}
Activité     : {company.get("activite", "")}
Ville        : {company.get("ville", "")}

Consignes :
- Première ligne : "Objet : ..." (objet de l'email)
- Corps court, 6-8 lignes max
- Ton professionnel mais direct
- Mentionner BTS SIO et la recherche d'alternance
- Ne pas inventer de poste ni d'informations
- Terminer par une formule de politesse"""

    resp = completion(
        model="ollama/llama3.2",
        messages=[{"role": "user", "content": prompt}],
        api_base="http://localhost:11434",
    )
    return resp["choices"][0]["message"]["content"].strip()


# ── App ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Leads Alternance", page_icon="💼", layout="wide")

st.title("Leads Alternance Informatique")
st.caption("Caussade · Montauban · Toulouse")

# Chargement initial dans session_state
if "df_full" not in st.session_state:
    st.session_state["df_full"] = load_csv()

df_full: pd.DataFrame = st.session_state["df_full"]

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Recherche")
    enrich_opt = st.checkbox(
        "Enrichissement web",
        value=ENRICH_DEFAULT,
        help="Site officiel, LinkedIn, email via DuckDuckGo (~3 s/entreprise).",
    )
    if st.button("Rechercher", type="primary", use_container_width=True):
        run_pipeline(enrich=enrich_opt)
        st.rerun()

    st.divider()
    st.header("Profil CV")
    cv_path = "data/cv_lucas.txt"
    if os.path.exists(cv_path):
        sz = os.path.getsize(cv_path)
        st.caption(f"cv_lucas.txt — {sz} octets")
    else:
        st.caption("cv_lucas.txt introuvable")
    if st.button("Actualiser profil CV", use_container_width=True,
                 help="Relance l'extraction Ollama si tu as mis à jour ton CV."):
        from cv_profile import get_profile
        get_profile(force_refresh=True)
        st.toast("Profil CV actualisé")

    st.divider()
    st.header("Filtres")

    if not df_full.empty:
        villes         = sorted(df_full["ville"].dropna().unique().tolist())
        filtre_villes  = st.multiselect("Ville", villes)
        filtre_score   = st.slider("Score minimum", 0, 100, 0)
        filtre_statuts = st.multiselect("Statut", STATUTS)
        filtre_actions = st.multiselect(
            "Action recommandée",
            ACTIONS,
            default=["contacter maintenant", "vérifier avant contact"],
        )
        interet_opts   = ["élevé", "moyen", "faible"]
        filtre_interet = st.multiselect("Intérêt pour toi", interet_opts)
    else:
        filtre_villes, filtre_score = [], 0
        filtre_statuts, filtre_actions, filtre_interet = [], [], []

# ── Corps principal ───────────────────────────────────────────────────────────

if df_full.empty:
    st.info("Aucune donnée. Lance **Rechercher** dans la barre latérale.")
    st.stop()

# Applique les filtres
df = df_full.copy()
if filtre_villes:
    df = df[df["ville"].isin(filtre_villes)]
if filtre_score > 0:
    df = df[df["score_final"] >= filtre_score]
if filtre_statuts:
    df = df[df["statut_contact"].isin(filtre_statuts)]
if filtre_actions and "action_recommandee" in df.columns:
    df = df[df["action_recommandee"].isin(filtre_actions)]
if filtre_interet and "interet_pour_lucas" in df.columns:
    df = df[df["interet_pour_lucas"].isin(filtre_interet)]

# Colonnes à afficher (intersection avec celles disponibles)
cols = [c for c in DISPLAY_COLS if c in df.columns]

st.caption(f"{len(df)} entreprises affichées sur {len(df_full)}")

# ── Tableau éditable ──────────────────────────────────────────────────────────

edited = st.data_editor(
    df[cols].reset_index(drop=True),
    column_config={
        "statut_contact": st.column_config.SelectboxColumn(
            "Statut",
            options=STATUTS,
            width="medium",
        ),
        "score_final": st.column_config.ProgressColumn(
            "Score",
            min_value=0,
            max_value=100,
            format="%d",
            width="small",
        ),
        "site_web":     st.column_config.LinkColumn("Site web",  display_text="Ouvrir", width="small"),
        "linkedin":     st.column_config.LinkColumn("LinkedIn",  display_text="Ouvrir", width="small"),
        "zone_score": st.column_config.NumberColumn("Zone", width="small",
            help="Score géo : 30=ville cible, 15=dept, négatif=hors zone"),
        "cv_match_score": st.column_config.ProgressColumn(
            "CV match", min_value=0, max_value=10, format="%d", width="small"),
        "action_recommandee": st.column_config.SelectboxColumn(
            "Action", options=ACTIONS, width="medium"),
        "company_type":       st.column_config.TextColumn("Type",         width="small"),
        "interet_pour_lucas": st.column_config.TextColumn("Intérêt",      width="small"),
        "site_type":          st.column_config.TextColumn("Site",         width="small"),
        "email":              st.column_config.TextColumn("Email",        width="medium"),
        "contact_confidence": st.column_config.TextColumn("Confiance",    width="small"),
        "telephone":          st.column_config.TextColumn("Tel.",          width="small"),
        "mission_probable":   st.column_config.TextColumn("Mission",      width="large"),
        "risque":             st.column_config.TextColumn("Risque",       width="medium"),
        "cv_match_reason":    st.column_config.TextColumn("Raison CV",    width="large"),
        "notes":              st.column_config.TextColumn("Notes",        width="large"),
        "date_contact":       st.column_config.TextColumn("Date contact (JJ/MM/AAAA)"),
        "dirigeant":          st.column_config.TextColumn("Dirigeant",    width="medium"),
        "raison_ia":          st.column_config.TextColumn("Analyse IA",   width="large"),
    },
    hide_index=True,
    use_container_width=True,
    key="leads_table",
    disabled=["nom", "ville", "score_final", "zone_score", "cv_match_score",
              "action_recommandee", "company_type", "interet_pour_lucas",
              "site_type", "contact_confidence", "mission_probable",
              "risque", "cv_match_reason", "raison_ia"],
)

# Bouton de sauvegarde explicite (plus fiable qu'un auto-save sur chaque rerun)
if st.button("Sauvegarder les modifications"):
    # Réinjecte la colonne siren (cachée dans l'éditeur) pour le merge
    edited_with_siren = df.reset_index(drop=True).copy()
    for col in edited.columns:
        edited_with_siren[col] = edited[col].values
    merge_and_save(edited_with_siren, df_full)
    st.session_state["df_full"] = load_csv()
    st.toast("Modifications sauvegardées", icon="✅")

# ── Générer un message ────────────────────────────────────────────────────────

st.divider()
st.subheader("Générer un message de candidature")

col_sel, col_btn = st.columns([4, 1])
with col_sel:
    noms = df["nom"].tolist()
    selected = st.selectbox(
        "Entreprise",
        noms,
        format_func=lambda n: (
            f"{n}  —  {df.loc[df['nom'] == n, 'ville'].values[0]}"
            if not df[df["nom"] == n].empty else n
        ),
        label_visibility="collapsed",
    )
with col_btn:
    st.write("")
    gen_btn = st.button("Générer", type="primary", use_container_width=True)

if gen_btn and selected:
    row = df[df["nom"] == selected]
    if not row.empty:
        with st.spinner("Ollama rédige le message…"):
            try:
                msg = generate_message(row.iloc[0].to_dict())
                st.session_state["last_msg"] = (selected, msg)
            except Exception as e:
                st.error(f"Erreur Ollama : {e}")

if "last_msg" in st.session_state:
    nom_msg, msg = st.session_state["last_msg"]
    st.text_area(
        f"Message pour {nom_msg} (à relire avant envoi)",
        msg,
        height=320,
    )
    st.download_button(
        "Télécharger (.txt)",
        msg,
        file_name=f"candidature_{nom_msg.replace(' ', '_')[:40]}.txt",
        mime="text/plain",
    )
