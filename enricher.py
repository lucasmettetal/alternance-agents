"""
Enrichit chaque entreprise avec : site officiel, LinkedIn, email, téléphone, page contact.
Stratégie en couches :
  1. DuckDuckGo → site officiel
  2. Scraping du site (7 chemins) → email + téléphone
  3. DDG ciblé → téléphone si toujours vide
  4. Déduction depuis le domaine → email si toujours vide (marqué "estimé")
"""

import re
import time
import requests as _requests
from urllib.parse import urlparse
from ddgs import DDGS

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; alternance-scout/1.0)"}

_AGGREGATEURS = [
    "societe.com", "pappers.fr", "infogreffe.fr", "kompass.fr", "kompass.com",
    "verif.com", "corporama.com", "manageo.fr", "dnb.com",
    "pagesjaunes.fr", "annuaire-entreprises.data.gouv.fr", "mappy.com",
    "sirene.fr", "linkedin.com", "facebook.com", "twitter.com",
    "instagram.com", "youtube.com", "google.com", "wikipedia.org",
    "leboncoin.fr", "indeed.fr", "welcometothejungle.com", "glassdoor",
    "lefigaro.fr", "cataloxy.", "lnr.fr", "eterritoire.fr",
    "viadeo.com", "crunchbase.com", "/personne-", "/dirigeant-",
    "careers.", "jobs.", "recrutement.", "talent.",   # sous-domaines RH
    "e-pro.fr", "annuaire.", "directory.", "bottin.",  # annuaires génériques
]

# Chemins testés dans l'ordre pour trouver email/téléphone
_CONTACT_PATHS = [
    "",               # page d'accueil
    "/contact",
    "/nous-contacter",
    "/contactez-nous",
    "/contact.html",
    "/contact.php",
    "/a-propos",
    "/mentions-legales",
    "/qui-sommes-nous",
]

_BAD_TLDS    = {"jpg","jpeg","png","gif","svg","webp","ico","css","js","json","woff","ttf","pdf","php"}
_BAD_DOMAINS = {"yandex.ru","maps.yandex","maps.google","wordpress.com",
                "googletagmanager","doubleclick","facebook.com","twitter.com"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _search(query: str, max_results: int = 5) -> list[dict]:
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []


def _fetch(url: str, timeout: int = 7) -> str:
    try:
        r = _requests.get(url, timeout=timeout, headers=_HEADERS, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def _is_valid_email(email: str) -> bool:
    tld = email.rsplit(".", 1)[-1].lower()
    if tld in _BAD_TLDS:
        return False
    return not any(bad in email.lower() for bad in _BAD_DOMAINS)


def _extract_email(text: str) -> str:
    for m in re.finditer(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", text, re.IGNORECASE):
        email = m.group().lower()
        if _is_valid_email(email):
            return email
    m2 = re.search(
        r"([\w.+-]+)\s*(?:\[at\]|\(at\)|\s+at\s+)\s*([\w.-]+\.[a-z]{2,})",
        text, re.IGNORECASE,
    )
    if m2:
        email = f"{m2.group(1)}@{m2.group(2)}".lower()
        if _is_valid_email(email):
            return email
    return ""


def _extract_phone(text: str) -> str:
    m = re.search(r"0[1-9](?:[\s.\-]?\d{2}){4}", text)
    return m.group().strip() if m else ""


def _is_aggregator(url: str) -> bool:
    return any(agg in url for agg in _AGGREGATEURS)


def _domain(site_web: str) -> str:
    return urlparse(site_web).netloc.replace("www.", "")


# ── Site officiel ─────────────────────────────────────────────────────────────

def find_website(nom: str, ville: str) -> str:
    for r in _search(f'"{nom}" {ville} site officiel'):
        url = r.get("href", "")
        if url and not _is_aggregator(url):
            return url
    return ""


# ── Scraping contacts ─────────────────────────────────────────────────────────

def scrape_contacts(site_web: str) -> tuple[str, str]:
    """
    Essaie 7+ chemins de pages pour extraire email et téléphone.
    Retourne (email, telephone).
    """
    email, phone = "", ""
    base = site_web.rstrip("/")

    for path in _CONTACT_PATHS:
        if email and phone:
            break
        html = _fetch(base + path)
        if not html:
            continue
        email = email or _extract_email(html)
        phone = phone or _extract_phone(html)

    return email, phone


# ── Fallbacks ─────────────────────────────────────────────────────────────────

def find_phone_ddg(nom: str, ville: str) -> str:
    """Cherche un numéro dans les extraits DuckDuckGo si le scraping a échoué."""
    for r in _search(f'"{nom}" {ville} telephone contact', max_results=5):
        phone = _extract_phone(r.get("body", ""))
        if phone:
            return phone
    return ""


def guess_email(site_web: str) -> str:
    """
    Déduit contact@{domain} depuis l'URL du site.
    Marqué "(estimé)" pour indiquer que c'est une déduction, pas une valeur scrapée.
    """
    domain = _domain(site_web)
    return f"contact@{domain} (estimé)" if domain else ""


_PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.fr", "yahoo.com", "hotmail.fr", "hotmail.com",
    "outlook.fr", "outlook.com", "orange.fr", "free.fr", "laposte.net",
    "sfr.fr", "wanadoo.fr", "live.fr", "live.com", "icloud.com",
}


def _email_quality(email: str) -> int:
    """0=absent/personnel, 1=estimé, 2=scrapé pro."""
    if not email:
        return 0
    clean = email.replace(" (estimé)", "").lower()
    domain = clean.split("@")[-1] if "@" in clean else ""
    if domain in _PERSONAL_EMAIL_DOMAINS:
        return 0
    return 1 if "(estimé)" in email else 2


def classify_site_type(url: str, nom: str) -> str:
    """Classe le site trouvé : officiel / annuaire / à vérifier / absent."""
    if not url:
        return "absent"
    if _is_aggregator(url):
        return "annuaire"
    try:
        domain_base = re.sub(r"[^a-z0-9]", "", urlparse(url).netloc.lower().replace("www.", "").split(".")[0])
        nom_key     = re.sub(r"[^a-z0-9]", "", nom.lower())[:14]
        if len(domain_base) >= 4 and (domain_base in nom_key or nom_key[:6] in domain_base):
            return "officiel"
    except Exception:
        pass
    return "à vérifier"


def compute_contact_confidence(company: dict) -> str:
    """Évalue la fiabilité des coordonnées : élevée / moyenne / faible."""
    pts = 0
    site_type = company.get("site_type", "absent")
    email     = company.get("email", "")
    phone     = company.get("telephone", "")

    if site_type == "officiel":
        pts += 2
    elif site_type == "à vérifier":
        pts += 1

    pts += _email_quality(email)

    if phone:
        pts += 1

    if pts >= 4:
        return "élevée"
    if pts >= 2:
        return "moyenne"
    return "faible"


def find_linkedin(nom: str) -> str:
    for r in _search(f'"{nom}" site:linkedin.com/company', max_results=3):
        url = r.get("href", "")
        if "linkedin.com/company" in url:
            return url
    return ""


# ── Point d'entrée ────────────────────────────────────────────────────────────

def enrich_company(company: dict, delay: float = 1.0) -> dict:
    """
    Enrichit company avec site_web, linkedin, email, telephone, page_contact.
    Modifie le dict en place.
    """
    nom   = company.get("nom", "")
    ville = company.get("ville", "")

    # Les EI n'ont presque jamais de site d'entreprise
    is_ei = str(company.get("nature_juridique", "")).startswith("1")

    # 1. Site officiel
    site = "" if is_ei else find_website(nom, ville)
    company["site_web"]  = site
    company["site_type"] = classify_site_type(site, nom)

    # 2. Scraping du site (email + téléphone)
    email, phone = "", ""
    if site:
        email, phone = scrape_contacts(site)
        company["page_contact"] = site.rstrip("/") + "/contact"
    else:
        company["page_contact"] = ""

    # 3. Téléphone : fallback DDG si toujours vide
    if not phone:
        phone = find_phone_ddg(nom, ville)

    # 4. Email : déduction depuis le domaine si toujours vide
    if not email and site:
        email = guess_email(site)

    company["email"]     = email
    company["telephone"] = phone

    time.sleep(delay)

    # 5. LinkedIn
    company["linkedin"] = find_linkedin(nom)

    time.sleep(delay)

    # 6. Fiabilité des contacts (après avoir tout rempli)
    company["contact_confidence"] = compute_contact_confidence(company)

    return company
