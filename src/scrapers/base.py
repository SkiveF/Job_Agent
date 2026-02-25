"""
Classe de base pour les scrapers d'offres d'emploi.
"""

import asyncio
import random
from abc import ABC, abstractmethod

from loguru import logger
from playwright.async_api import async_playwright, Browser, Page

from src.config import settings
from src.models import JobOffer


class BaseScraper(ABC):
    """Scraper de base avec gestion anti-détection."""

    name: str = "base"

    def __init__(self):
        self.browser: Browser | None = None
        self.offers: list[JobOffer] = []

    async def _init_browser(self) -> Browser:
        """Initialise un navigateur Playwright en mode stealth."""
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        logger.info(f"[{self.name}] Navigateur initialisé")
        return browser

    async def _new_page(self) -> Page:
        """Crée une nouvelle page avec des headers réalistes."""
        if not self.browser:
            self.browser = await self._init_browser()

        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
        )
        page = await context.new_page()

        # Masquer webdriver
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        return page

    async def _human_delay(self):
        """Simule un délai humain entre les actions."""
        delay = random.uniform(settings.min_delay, settings.max_delay)
        logger.debug(f"[{self.name}] Pause de {delay:.1f}s")
        await asyncio.sleep(delay)

    async def _random_scroll(self, page: Page):
        """Scroll aléatoire pour simuler un comportement humain."""
        scroll_amount = random.randint(200, 800)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await asyncio.sleep(random.uniform(0.5, 1.5))

    @abstractmethod
    async def search(self, keywords: list[str], location: str, **kwargs) -> list[JobOffer]:
        """Recherche des offres selon les critères."""
        ...

    @abstractmethod
    async def parse_offer(self, page: Page, url: str) -> JobOffer | None:
        """Parse une offre individuelle."""
        ...

    async def close(self):
        """Ferme le navigateur."""
        if self.browser:
            await self.browser.close()
            logger.info(f"[{self.name}] Navigateur fermé")
