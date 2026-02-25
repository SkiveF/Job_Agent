"""
Orchestrateur principal : coordonne scraping → matching → candidature → tracking.
"""

import asyncio
from loguru import logger

from src.config import load_criteria, load_profile, settings
from src.models import ApplicationStatus, JobSource
from src.scrapers.indeed import IndeedScraper
from src.scrapers.wttj import WTTJScraper
from src.matching.engine import MatchingEngine
from src.matching.esn_detector import get_company_type_label
from src.applicator.indeed import IndeedApplicator
from src.applicator.wttj import WTTJApplicator
from src.tracker.tracker import ApplicationTracker


class JobAgent:
    """Agent principal qui orchestre tout le pipeline."""

    def __init__(self):
        self.criteria = load_criteria()
        self.profile = load_profile()
        self.tracker = ApplicationTracker()
        self.matching = MatchingEngine(self.criteria, self.profile)
        self.mode = settings.application_mode

        # Scrapers
        self.scrapers = {}
        sites = self.criteria.get("sites", {})
        if sites.get("indeed", {}).get("actif", False):
            self.scrapers["indeed"] = IndeedScraper()
        if sites.get("wttj", {}).get("actif", False):
            self.scrapers["wttj"] = WTTJScraper()

        # Applicators
        self.applicators = {
            "indeed": IndeedApplicator(self.profile),
            "wttj": WTTJApplicator(self.profile),
        }

        logger.info(
            f"[agent] Initialisé | Mode: {self.mode} | "
            f"Sites: {list(self.scrapers.keys())}"
        )

    async def run(self):
        """Exécute le pipeline complet."""
        logger.info("=" * 60)
        logger.info("[agent] DÉMARRAGE DU PIPELINE")
        logger.info("=" * 60)

        # ── Étape 1 : Scraping ────────────────────────────────────
        all_offers = await self._scrape()
        if not all_offers:
            logger.warning("[agent] Aucune offre trouvée. Arrêt.")
            return

        # ── Étape 2 : Filtrage des doublons déjà postulés ────────
        new_offers = [
            o for o in all_offers
            if not self.tracker.is_already_applied(o.url)
        ]
        logger.info(
            f"[agent] {len(new_offers)} nouvelles offres "
            f"(déjà postulé: {len(all_offers) - len(new_offers)})"
        )

        # ── Étape 3 : Matching ────────────────────────────────────
        matched = self.matching.filter_offers(new_offers)
        if not matched:
            logger.info("[agent] Aucune offre ne correspond aux critères.")
            return

        # Sauvegarder toutes les candidatures matchées
        for app in matched:
            self.tracker.save_application(app)

        # Compter ESN vs Direct
        from src.models import CompanyType
        esn_count = sum(1 for a in matched if a.job.company_type == CompanyType.ESN)
        direct_count = sum(1 for a in matched if a.job.company_type == CompanyType.DIRECT)
        unknown_count = sum(1 for a in matched if a.job.company_type == CompanyType.UNKNOWN)

        logger.info(
            f"[agent] {len(matched)} offres correspondent aux critères "
            f"(🏢 ESN: {esn_count} | 🏠 Direct: {direct_count} | ❓: {unknown_count})"
        )
        self._print_offers(matched)

        # ── Étape 4 : Candidature ─────────────────────────────────
        await self._apply(matched)

        # ── Étape 5 : Résumé ──────────────────────────────────────
        self._print_summary()

    async def scrape_only(self):
        """Scrape et filtre sans postuler (mode preview)."""
        logger.info("[agent] Mode PREVIEW — scraping + matching uniquement")
        all_offers = await self._scrape()

        new_offers = [
            o for o in all_offers
            if not self.tracker.is_already_applied(o.url)
        ]

        matched = self.matching.filter_offers(new_offers)
        for app in matched:
            self.tracker.save_application(app)

        self._print_offers(matched)
        self._print_summary()
        return matched

    async def _scrape(self):
        """Exécute le scraping sur tous les sites actifs."""
        recherche = self.criteria.get("recherche", {})
        keywords = recherche.get("mots_cles", [])
        cities = recherche.get("localisation", {}).get("villes", ["Paris"])
        sites_config = self.criteria.get("sites", {})

        all_offers = []

        for site_name, scraper in self.scrapers.items():
            max_pages = sites_config.get(site_name, {}).get("max_pages", 3)
            for city in cities:
                try:
                    offers = await scraper.search(
                        keywords=keywords,
                        location=city,
                        max_pages=max_pages,
                    )
                    all_offers.extend(offers)
                except Exception as e:
                    logger.error(f"[agent] Erreur scraping {site_name}/{city}: {e}")

            await scraper.close()

        # Dédupliquer par URL
        seen_urls = set()
        unique = []
        for o in all_offers:
            if o.url not in seen_urls:
                seen_urls.add(o.url)
                unique.append(o)

        logger.info(f"[agent] Total scrapé: {len(unique)} offres uniques")
        return unique

    async def _apply(self, matched):
        """Postule aux offres matchées."""
        logger.info(f"[agent] Début des candidatures en mode '{self.mode}'")

        for i, app in enumerate(matched, 1):
            job = app.job
            source = job.source.value  # "indeed" ou "wttj"
            applicator = self.applicators.get(source)

            if not applicator:
                logger.warning(f"[agent] Pas d'applicator pour {source}")
                continue

            logger.info(
                f"\n[agent] ── Candidature {i}/{len(matched)} ──\n"
                f"  Poste   : {job.title}\n"
                f"  Société : {job.company}\n"
                f"  Type    : {get_company_type_label(job.company_type)}\n"
                f"  Lieu    : {job.location}\n"
                f"  Score   : {app.match_score}/100\n"
                f"  URL     : {job.url}"
            )

            new_status = await applicator.apply(app, mode=self.mode)
            app.status = new_status
            self.tracker.save_application(app)

            logger.info(f"[agent] Statut: {new_status.value}")

        # Fermer les applicators
        for applicator in self.applicators.values():
            await applicator.close()

    def _print_offers(self, matched):
        """Affiche les offres matchées."""
        logger.info("\n" + "=" * 60)
        logger.info(f"  OFFRES CORRESPONDANTES ({len(matched)})")
        logger.info("=" * 60)

        for i, app in enumerate(matched, 1):
            job = app.job
            type_label = get_company_type_label(job.company_type)
            logger.info(
                f"\n  {i}. {job.title}"
                f"\n     {job.company} — {job.location}"
                f"\n     {type_label}"
                f"\n     Score: {app.match_score}/100 | {job.source.value}"
                f"\n     {job.url}"
            )

    def _print_summary(self):
        """Affiche le résumé des statistiques."""
        stats = self.tracker.get_stats()
        logger.info("\n" + "=" * 60)
        logger.info("  RÉSUMÉ")
        logger.info("=" * 60)
        logger.info(f"  Offres scrapées     : {stats['total_jobs_scraped']}")
        logger.info(f"  Candidatures totales: {stats['total_applications']}")
        logger.info(f"  Score moyen         : {stats['avg_match_score']}/100")
        for status, count in stats.get("by_status", {}).items():
            logger.info(f"    {status:<12}: {count}")


async def main():
    """Point d'entrée principal."""
    import sys

    agent = JobAgent()

    if "--preview" in sys.argv:
        await agent.scrape_only()
    else:
        await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
