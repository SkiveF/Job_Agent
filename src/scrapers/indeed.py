"""
Scraper pour Indeed France (fr.indeed.com).
"""

import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from loguru import logger
from playwright.async_api import Page

from src.models import JobOffer, JobSource, ContractType, RemoteType
from src.scrapers.base import BaseScraper


class IndeedScraper(BaseScraper):
    name = "indeed"

    def __init__(self):
        super().__init__()
        self.base_url = "https://fr.indeed.com"

    def _build_search_url(self, keyword: str, location: str, page: int = 0) -> str:
        """Construit l'URL de recherche Indeed."""
        kw = quote_plus(keyword)
        loc = quote_plus(location)
        start = page * 10
        url = f"{self.base_url}/jobs?q={kw}&l={loc}&start={start}&sort=date"
        return url

    async def search(
        self,
        keywords: list[str],
        location: str,
        max_pages: int = 5,
        **kwargs,
    ) -> list[JobOffer]:
        """Cherche des offres sur Indeed."""
        all_offers: list[JobOffer] = []

        page = await self._new_page()

        for keyword in keywords:
            logger.info(f"[indeed] Recherche: '{keyword}' à '{location}'")

            for page_num in range(max_pages):
                url = self._build_search_url(keyword, location, page_num)
                logger.debug(f"[indeed] Page {page_num + 1}: {url}")

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await self._human_delay()
                    await self._random_scroll(page)

                    # Extraire les cartes d'offres
                    job_cards = await page.query_selector_all(
                        'div.job_seen_beacon, div.jobsearch-ResultsList > li'
                    )

                    if not job_cards:
                        logger.warning(f"[indeed] Aucune offre trouvée page {page_num + 1}")
                        break

                    for card in job_cards:
                        try:
                            offer = await self._parse_card(card)
                            if offer and offer.url not in {o.url for o in all_offers}:
                                all_offers.append(offer)
                        except Exception as e:
                            logger.debug(f"[indeed] Erreur parsing carte: {e}")
                            continue

                    logger.info(
                        f"[indeed] '{keyword}' page {page_num + 1}: "
                        f"{len(job_cards)} cartes, {len(all_offers)} offres total"
                    )

                    await self._human_delay()

                except Exception as e:
                    logger.error(f"[indeed] Erreur page {page_num + 1}: {e}")
                    break

        await page.close()
        logger.info(f"[indeed] Total: {len(all_offers)} offres trouvées")
        self.offers = all_offers
        return all_offers

    async def _parse_card(self, card) -> JobOffer | None:
        """Parse une carte d'offre depuis la page de résultats."""
        # Titre
        title_el = await card.query_selector("h2.jobTitle a, a.jcs-JobTitle")
        if not title_el:
            return None
        title = (await title_el.inner_text()).strip()
        href = await title_el.get_attribute("href")
        if not href:
            return None
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        # Entreprise
        company_el = await card.query_selector(
            "span[data-testid='company-name'], span.companyName"
        )
        company = (await company_el.inner_text()).strip() if company_el else "Inconnu"

        # Localisation
        location_el = await card.query_selector(
            "div[data-testid='text-location'], div.companyLocation"
        )
        location = (await location_el.inner_text()).strip() if location_el else ""

        # Salaire (optionnel)
        salary_el = await card.query_selector(
            "div.salary-snippet-container, div[data-testid='attribute_snippet_testid']"
        )
        salary_min, salary_max = None, None
        if salary_el:
            salary_text = await salary_el.inner_text()
            salary_min, salary_max = self._parse_salary(salary_text)

        # Description courte
        snippet_el = await card.query_selector("div.job-snippet, table.jobCardShelfContainer")
        description = ""
        if snippet_el:
            description = (await snippet_el.inner_text()).strip()

        # Date
        date_el = await card.query_selector("span.date, span[data-testid='myJobsStateDate']")
        date_posted = None
        if date_el:
            date_text = await date_el.inner_text()
            date_posted = self._parse_date(date_text)

        # Détecter remote
        remote = RemoteType.UNKNOWN
        full_text = f"{title} {location} {description}".lower()
        if "télétravail" in full_text or "remote" in full_text:
            if "hybride" in full_text or "partiel" in full_text:
                remote = RemoteType.PARTIAL
            else:
                remote = RemoteType.FULL

        return JobOffer(
            title=title,
            company=company,
            location=location,
            description=description,
            url=url,
            source=JobSource.INDEED,
            salary_min=salary_min,
            salary_max=salary_max,
            remote=remote,
            date_posted=date_posted,
        )

    async def parse_offer(self, page: Page, url: str) -> JobOffer | None:
        """Parse une offre individuelle depuis sa page dédiée."""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay()

            title_el = await page.query_selector("h1.jobsearch-JobInfoHeader-title")
            title = (await title_el.inner_text()).strip() if title_el else "Sans titre"

            company_el = await page.query_selector(
                "div[data-testid='inlineHeader-companyName'] a, "
                "div.jobsearch-InlineCompanyRating a"
            )
            company = (await company_el.inner_text()).strip() if company_el else "Inconnu"

            desc_el = await page.query_selector("div#jobDescriptionText")
            description = (await desc_el.inner_text()).strip() if desc_el else ""

            location_el = await page.query_selector(
                "div[data-testid='inlineHeader-companyLocation'], "
                "div.jobsearch-InlineCompanyRating + div"
            )
            location = (await location_el.inner_text()).strip() if location_el else ""

            return JobOffer(
                title=title,
                company=company,
                location=location,
                description=description,
                url=url,
                source=JobSource.INDEED,
            )
        except Exception as e:
            logger.error(f"[indeed] Erreur parsing offre {url}: {e}")
            return None

    @staticmethod
    def _parse_salary(text: str) -> tuple[int | None, int | None]:
        """Extrait les valeurs de salaire depuis un texte."""
        numbers = re.findall(r"[\d\s]+", text.replace("\u202f", "").replace(" ", ""))
        cleaned = [int(n.strip().replace(" ", "")) for n in numbers if n.strip()]

        if len(cleaned) >= 2:
            return cleaned[0], cleaned[1]
        elif len(cleaned) == 1:
            return cleaned[0], None
        return None, None

    @staticmethod
    def _parse_date(text: str) -> datetime | None:
        """Convertit 'il y a X jours' en datetime."""
        text = text.lower().strip()
        match = re.search(r"(\d+)", text)
        if match:
            days = int(match.group(1))
            return datetime.now() - timedelta(days=days)
        if "aujourd" in text or "just" in text:
            return datetime.now()
        return None
