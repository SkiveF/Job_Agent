"""
Moteur de matching : filtre et score les offres selon les critères utilisateur.
Pas d'IA ici — filtrage basé sur des règles métier.
"""

import re
from datetime import datetime, timedelta

from loguru import logger

from src.models import (
    JobOffer,
    Application,
    ApplicationStatus,
    CompanyType,
    ContractType,
    RemoteType,
)
from src.matching.esn_detector import detect_company_type, get_company_type_label


# Villes et communes d'Île-de-France (pour matching localisation)
IDF_KEYWORDS = [
    "paris", "île-de-france", "ile-de-france", "idf",
    "la défense", "la defense", "courbevoie", "puteaux", "nanterre",
    "boulogne", "issy", "levallois", "neuilly", "clichy",
    "montreuil", "saint-denis", "vincennes", "ivry", "vitry",
    "créteil", "creteil", "versailles", "massy", "évry", "evry",
    "noisy", "fontenay", "malakoff", "montrouge", "gentilly",
    "arcueil", "cachan", "charenton", "saint-ouen", "pantin",
    "aubervilliers", "bobigny", "rueil", "suresnes", "clamart",
    "chatillon", "vanves", "colombes", "asnières", "asnieres",
    "gennevilliers", "argenteuil", "sartrouville", "poissy",
    "saint-germain", "rambouillet", "meaux", "melun", "fontainebleau",
    "cergy", "pontoise", "bezons", "clayes-sous-bois",
    "bois-colombes", "vélizy", "velizy",
]


class MatchingEngine:
    """Filtre et score les offres d'emploi selon les critères définis."""

    def __init__(self, criteria: dict, profile: dict):
        self.criteria = criteria.get("recherche", {})
        self.profile = profile
        self._keywords = [k.lower() for k in self.criteria.get("mots_cles", [])]
        self._excluded = [k.lower() for k in self.criteria.get("mots_cles_exclus", [])]
        self._cities = [
            c.lower() for c in self.criteria.get("localisation", {}).get("villes", [])
        ]
        self._contract_types = [
            c.upper() for c in self.criteria.get("type_contrat", [])
        ]
        self._remote_config = self.criteria.get("remote", {})
        self._salary_min = self.criteria.get("salaire", {}).get("minimum", 0)
        self._max_experience = self.criteria.get("experience", {}).get("maximum", 99)
        self._max_age_days = self.criteria.get("anciennete_max_jours", 30)

        # Préférence ESN / Direct
        type_entreprise = self.criteria.get("type_entreprise", {})
        self._company_pref = type_entreprise.get("preference", "tous").lower()  # "esn", "direct", "tous"
        self._esn_eliminatory = type_entreprise.get("eliminatoire", False)  # Si True, exclut les ESN (ou direct)

    def evaluate(self, offer: JobOffer) -> Application:
        """Évalue une offre et retourne une Application avec un score."""
        score = 0.0
        details = {}

        # ── 0. Texte complet pour analyse ─────────────────────
        text = f"{offer.title} {offer.description}".lower()
        url_lower = offer.url.lower()

        # ── 1. Mots-clés exclus (ÉLIMINATOIRE) ───────────────────
        # Vérifier dans le titre, la description ET l'URL
        for excl in self._excluded:
            if excl in text or excl in url_lower:
                return Application(
                    job=offer,
                    status=ApplicationStatus.REJECTED,
                    match_score=0,
                    match_details={"raison": f"Mot-clé exclu: '{excl}'"},
                )

        # ── 2. Pertinence du titre (ÉLIMINATOIRE) ────────────────
        # Le titre ou l'URL doit contenir au moins un mot-clé
        title_lower = offer.title.lower()
        title_relevant = any(kw in title_lower or kw in url_lower for kw in self._keywords)
        if not title_relevant:
            return Application(
                job=offer,
                status=ApplicationStatus.REJECTED,
                match_score=0,
                match_details={"raison": f"Titre non pertinent: '{offer.title}'"},
            )

        # ── 3. Localisation (ÉLIMINATOIRE) ────────────────────────
        # L'offre DOIT être en Île-de-France
        loc_lower = offer.location.lower()
        # Vérifier aussi dans l'URL (souvent la ville est dans l'URL WTTJ)
        loc_text = f"{loc_lower} {url_lower}"
        loc_match = any(city in loc_text for city in IDF_KEYWORDS)
        if not loc_match:
            return Application(
                job=offer,
                status=ApplicationStatus.REJECTED,
                match_score=0,
                match_details={"raison": f"Hors Île-de-France: '{offer.location}'"},
            )

        # ── 4. Mots-clés recherchés (0-30 pts) ───────────────────
        matched_kw = [kw for kw in self._keywords if kw in text or kw in url_lower]
        kw_score = min(30, (len(matched_kw) / max(len(self._keywords), 1)) * 30)
        score += kw_score
        details["keywords"] = {
            "matched": matched_kw,
            "score": round(kw_score, 1),
        }

        # ── 5. Localisation (0-20 pts) ────────────────────────────
        loc_score = 20  # Déjà validé comme IDF ci-dessus
        score += loc_score
        details["location"] = {
            "offer": offer.location,
            "match": True,
            "score": loc_score,
        }

        # ── 4. Type de contrat (0-15 pts) ─────────────────────────
        contract_match = (
            offer.contract_type == ContractType.UNKNOWN
            or offer.contract_type.value.upper() in self._contract_types
        )
        contract_score = 15 if contract_match else 0
        score += contract_score
        details["contract"] = {
            "offer": offer.contract_type.value,
            "match": contract_match,
            "score": contract_score,
        }

        # ── 5. Remote (0-15 pts) ──────────────────────────────────
        remote_ok = True
        if self._remote_config.get("accepte", False):
            min_remote = self._remote_config.get("minimum", "aucun")
            if min_remote == "full" and offer.remote not in (
                RemoteType.FULL,
                RemoteType.UNKNOWN,
            ):
                remote_ok = False
            elif min_remote == "partiel" and offer.remote == RemoteType.NONE:
                remote_ok = False
        remote_score = 15 if remote_ok else 0
        score += remote_score
        details["remote"] = {
            "offer": offer.remote.value,
            "match": remote_ok,
            "score": remote_score,
        }

        # ── 6. Salaire (0-10 pts) ─────────────────────────────────
        salary_ok = True
        if self._salary_min and offer.salary_max:
            salary_ok = offer.salary_max >= self._salary_min
        elif self._salary_min and offer.salary_min:
            salary_ok = offer.salary_min >= self._salary_min * 0.8  # 20% tolérance
        salary_score = 10 if salary_ok else 0
        score += salary_score
        details["salary"] = {
            "offer_min": offer.salary_min,
            "offer_max": offer.salary_max,
            "criteria_min": self._salary_min,
            "match": salary_ok,
            "score": salary_score,
        }

        # ── 7. Expérience (0-5 pts) ───────────────────────────────
        exp_ok = True
        if offer.experience_required and offer.experience_required > self._max_experience:
            exp_ok = False
        exp_score = 5 if exp_ok else 0
        score += exp_score
        details["experience"] = {
            "required": offer.experience_required,
            "max_accepted": self._max_experience,
            "match": exp_ok,
            "score": exp_score,
        }

        # ── 8. Fraîcheur de l'offre (0-5 pts) ────────────────────
        date_ok = True
        if offer.date_posted:
            age = (datetime.now() - offer.date_posted).days
            date_ok = age <= self._max_age_days
        date_score = 5 if date_ok else 2  # Bonus si récent
        score += date_score
        details["freshness"] = {
            "date_posted": str(offer.date_posted) if offer.date_posted else None,
            "max_days": self._max_age_days,
            "match": date_ok,
            "score": date_score,
        }

        # ── 9. Type d'entreprise ESN/Direct ──────────────────────
        company_type = detect_company_type(offer.company, offer.description)
        offer.company_type = company_type
        type_label = get_company_type_label(company_type)

        # Filtrage éliminatoire si configuré
        if self._esn_eliminatory and self._company_pref != "tous":
            if self._company_pref == "direct" and company_type == CompanyType.ESN:
                return Application(
                    job=offer,
                    status=ApplicationStatus.REJECTED,
                    match_score=0,
                    match_details={"raison": f"ESN exclue: '{offer.company}' ({type_label})"},
                )
            elif self._company_pref == "esn" and company_type == CompanyType.DIRECT:
                return Application(
                    job=offer,
                    status=ApplicationStatus.REJECTED,
                    match_score=0,
                    match_details={"raison": f"Client final exclu: '{offer.company}' ({type_label})"},
                )

        # Bonus/malus selon la préférence (ajuste le score de ±5)
        company_score = 0
        if self._company_pref == "direct":
            if company_type == CompanyType.DIRECT:
                company_score = 5
            elif company_type == CompanyType.ESN:
                company_score = -5
        elif self._company_pref == "esn":
            if company_type == CompanyType.ESN:
                company_score = 5
            elif company_type == CompanyType.DIRECT:
                company_score = -5
        score += company_score

        details["company_type"] = {
            "type": company_type.value,
            "label": type_label,
            "preference": self._company_pref,
            "eliminatory": self._esn_eliminatory,
            "score": company_score,
        }

        # ── Résultat final ────────────────────────────────────────
        final_score = round(score, 1)
        status = (
            ApplicationStatus.MATCHED if final_score >= 50
            else ApplicationStatus.REJECTED
        )

        logger.debug(
            f"[matching] {offer.title} @ {offer.company} → {final_score}/100 ({status.value})"
        )

        return Application(
            job=offer,
            status=status,
            match_score=final_score,
            match_details=details,
        )

    def filter_offers(self, offers: list[JobOffer]) -> list[Application]:
        """Filtre et trie une liste d'offres par score décroissant."""
        applications = [self.evaluate(offer) for offer in offers]
        matched = [a for a in applications if a.status == ApplicationStatus.MATCHED]
        matched.sort(key=lambda a: a.match_score, reverse=True)

        logger.info(
            f"[matching] {len(matched)}/{len(offers)} offres correspondent aux critères"
        )
        return matched

    def get_rejected(self, offers: list[JobOffer]) -> list[Application]:
        """Retourne les offres rejetées (pour debug/info)."""
        applications = [self.evaluate(offer) for offer in offers]
        return [a for a in applications if a.status == ApplicationStatus.REJECTED]
