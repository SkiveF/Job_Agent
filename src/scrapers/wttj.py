"""
Scraper pour Welcome to the Jungle (WTTJ).
"""

import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from loguru import logger
from playwright.async_api import Page

from src.models import JobOffer, JobSource, ContractType, RemoteType
from src.scrapers.base import BaseScraper


class WTTJScraper(BaseScraper):
    name = "wttj"

    def __init__(self):
        super().__init__()
        self.base_url = "https://www.welcometothejungle.com/fr/jobs"

    def _build_search_url(self, keyword: str, location: str, page: int = 1) -> str:
        """Construit l'URL de recherche WTTJ."""
        kw = quote_plus(keyword)
        url = f"{self.base_url}?query={kw}&page={page}&aroundQuery={quote_plus(location)}"
        return url

    async def search(
        self,
        keywords: list[str],
        location: str,
        max_pages: int = 5,
        **kwargs,
    ) -> list[JobOffer]:
        """Cherche des offres sur Welcome to the Jungle."""
        all_offers: list[JobOffer] = []

        page = await self._new_page()

        for keyword in keywords:
            logger.info(f"[wttj] Recherche: '{keyword}' à '{location}'")

            for page_num in range(1, max_pages + 1):
                url = self._build_search_url(keyword, location, page_num)
                logger.debug(f"[wttj] Page {page_num}: {url}")

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await self._human_delay()
                    await self._random_scroll(page)

                    # Gestion cookie banner
                    if page_num == 1:
                        try:
                            cookie_btn = await page.query_selector(
                                "button[data-testid='cookie-consent-accept-all'], "
                                "button:has-text('Tout accepter')"
                            )
                            if cookie_btn:
                                await cookie_btn.click()
                                await self._human_delay()
                        except Exception:
                            pass

                    # Extraire les cartes d'offres
                    job_cards = await page.query_selector_all(
                        'li[data-testid="search-results-list-item-wrapper"], '
                        'div[class*="SearchResults"] > ul > li, '
                        'article[data-testid*="job"]'
                    )

                    if not job_cards:
                        logger.warning(f"[wttj] Aucune offre trouvée page {page_num}")
                        break

                    for card in job_cards:
                        try:
                            offer = await self._parse_card(card)
                            if offer and offer.url not in {o.url for o in all_offers}:
                                all_offers.append(offer)
                        except Exception as e:
                            logger.debug(f"[wttj] Erreur parsing carte: {e}")
                            continue

                    logger.info(
                        f"[wttj] '{keyword}' page {page_num}: "
                        f"{len(job_cards)} cartes, {len(all_offers)} offres total"
                    )

                    await self._human_delay()

                except Exception as e:
                    logger.error(f"[wttj] Erreur page {page_num}: {e}")
                    break

        await page.close()
        logger.info(f"[wttj] Total: {len(all_offers)} offres trouvées")
        self.offers = all_offers
        return all_offers

    async def _parse_card(self, card) -> JobOffer | None:
        """Parse une carte WTTJ depuis les résultats de recherche."""
        # Lien principal
        link_el = await card.query_selector("a[href*='/jobs/']")
        if not link_el:
            return None

        href = await link_el.get_attribute("href")
        if not href:
            return None

        url = href if href.startswith("http") else f"https://www.welcometothejungle.com{href}"

        # Titre
        title_el = await card.query_selector(
            "h4, span[data-testid='job-card-title'], "
            "div[role='heading']"
        )
        title = (await title_el.inner_text()).strip() if title_el else "Sans titre"

        # Entreprise
        company_el = await card.query_selector(
            "span[data-testid='job-card-company-name'], "
            "h3, p:first-of-type"
        )
        company = (await company_el.inner_text()).strip() if company_el else "Inconnu"

        # Localisation
        location_el = await card.query_selector(
            "span[data-testid='job-card-location'], "
            "span:has-text('Paris'), span:has-text('Lyon'), span:has-text('Remote')"
        )
        location = (await location_el.inner_text()).strip() if location_el else ""

        # Type de contrat
        contract_el = await card.query_selector(
            "span[data-testid='job-card-contract-type'], "
            "span:has-text('CDI'), span:has-text('CDD')"
        )
        contract_type = ContractType.UNKNOWN
        if contract_el:
            ct_text = (await contract_el.inner_text()).strip().upper()
            for ct in ContractType:
                if ct.value.upper() in ct_text:
                    contract_type = ct
                    break

        # Remote
        remote = RemoteType.UNKNOWN
        card_text = (await card.inner_text()).lower()
        if "télétravail total" in card_text or "full remote" in card_text:
            remote = RemoteType.FULL
        elif "télétravail partiel" in card_text or "hybride" in card_text:
            remote = RemoteType.PARTIAL
        elif "sur site" in card_text or "pas de télétravail" in card_text:
            remote = RemoteType.NONE

        # Salaire
        salary_min, salary_max = None, None
        salary_match = re.findall(r"(\d[\d\s]*)\s*[k€K]", card_text)
        if salary_match:
            values = [int(s.replace(" ", "")) for s in salary_match]
            if values:
                # Si c'est en K, multiplier par 1000
                salary_min = values[0] * 1000 if values[0] < 1000 else values[0]
                if len(values) > 1:
                    salary_max = values[1] * 1000 if values[1] < 1000 else values[1]

        return JobOffer(
            title=title,
            company=company,
            location=location,
            url=url,
            source=JobSource.WTTJ,
            salary_min=salary_min,
            salary_max=salary_max,
            contract_type=contract_type,
            remote=remote,
        )

    async def parse_offer(self, page: Page, url: str) -> JobOffer | None:
        """Parse une offre WTTJ depuis sa page dédiée."""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay()

            title_el = await page.query_selector("h2[data-testid='job-section-title'], h1")
            title = (await title_el.inner_text()).strip() if title_el else "Sans titre"

            company_el = await page.query_selector(
                "a[data-testid='job-company-name'], "
                "span[data-testid='job-header-company-name']"
            )
            company = (await company_el.inner_text()).strip() if company_el else "Inconnu"

            desc_el = await page.query_selector(
                "div[data-testid='job-section-description'], "
                "section[data-testid='job-section-description']"
            )
            description = (await desc_el.inner_text()).strip() if desc_el else ""

            location_el = await page.query_selector("span[data-testid='job-header-location']")
            location = (await location_el.inner_text()).strip() if location_el else ""

            return JobOffer(
                title=title,
                company=company,
                location=location,
                description=description,
                url=url,
                source=JobSource.WTTJ,
            )
        except Exception as e:
            logger.error(f"[wttj] Erreur parsing offre {url}: {e}")
            return None
