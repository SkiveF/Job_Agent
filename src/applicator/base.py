"""
Classe de base pour les modules de candidature.
"""

import random
import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger
from playwright.async_api import async_playwright, Browser, Page

from src.config import settings
from src.models import Application, ApplicationStatus


class BaseApplicator(ABC):
    """Base class pour postuler sur un site."""

    name: str = "base"

    def __init__(self, profile: dict):
        self.profile = profile
        self.browser: Browser | None = None
        self.cv_path: Path | None = None

        # Charger le chemin du CV
        cv_file = profile.get("cv", {}).get("fichier_pdf", "")
        if cv_file:
            self.cv_path = Path(cv_file).resolve()

    async def _init_browser(self, headless: bool = False) -> Browser:
        """Initialise le navigateur. headless=False pour mode semi-auto."""
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized",
            ],
        )
        return browser

    async def _new_page(self, headless: bool = False) -> Page:
        """Crée une page avec context réaliste."""
        if not self.browser:
            self.browser = await self._init_browser(headless=headless)

        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
        )
        return await context.new_page()

    async def _human_delay(self, min_s: float | None = None, max_s: float | None = None):
        """Délai aléatoire pour simuler un humain."""
        lo = min_s or settings.min_delay
        hi = max_s or settings.max_delay
        await asyncio.sleep(random.uniform(lo, hi))

    async def _human_type(self, page: Page, selector: str, text: str):
        """Tape du texte avec une vitesse humaine."""
        el = await page.query_selector(selector)
        if el:
            await el.click()
            for char in text:
                await page.keyboard.type(char, delay=random.randint(30, 120))
            await asyncio.sleep(random.uniform(0.3, 0.8))

    async def _fill_field(self, page: Page, selector: str, value: str):
        """Remplit un champ de formulaire."""
        try:
            el = await page.query_selector(selector)
            if el:
                await el.click()
                await el.fill("")  # Clear
                await el.fill(value)
                logger.debug(f"[{self.name}] Champ rempli: {selector}")
                return True
        except Exception as e:
            logger.debug(f"[{self.name}] Impossible de remplir {selector}: {e}")
        return False

    async def _upload_cv(self, page: Page, selector: str = 'input[type="file"]'):
        """Upload le CV PDF."""
        if not self.cv_path or not self.cv_path.exists():
            logger.warning(f"[{self.name}] CV non trouvé: {self.cv_path}")
            return False

        try:
            file_input = await page.query_selector(selector)
            if file_input:
                await file_input.set_input_files(str(self.cv_path))
                logger.info(f"[{self.name}] CV uploadé: {self.cv_path.name}")
                return True
        except Exception as e:
            logger.error(f"[{self.name}] Erreur upload CV: {e}")
        return False

    @abstractmethod
    async def apply_semi_auto(self, application: Application) -> ApplicationStatus:
        """
        Mode semi-auto: prépare tout, ouvre le navigateur, attend validation humaine.
        Retourne le nouveau statut.
        """
        ...

    @abstractmethod
    async def apply_full_auto(self, application: Application) -> ApplicationStatus:
        """
        Mode full-auto: postule automatiquement sans intervention.
        Retourne le nouveau statut.
        """
        ...

    async def apply(self, application: Application, mode: str = "semi-auto") -> ApplicationStatus:
        """Point d'entrée: postule selon le mode choisi."""
        logger.info(
            f"[{self.name}] Candidature {mode} → "
            f"{application.job.title} @ {application.job.company}"
        )

        try:
            if mode == "full-auto":
                return await self.apply_full_auto(application)
            else:
                return await self.apply_semi_auto(application)
        except Exception as e:
            logger.error(f"[{self.name}] Erreur candidature: {e}")
            return ApplicationStatus.FAILED

    async def close(self):
        if self.browser:
            await self.browser.close()
