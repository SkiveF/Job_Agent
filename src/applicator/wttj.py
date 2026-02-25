"""
Module de candidature pour Welcome to the Jungle.
"""

import asyncio
from datetime import datetime

from loguru import logger

from src.models import Application, ApplicationStatus
from src.applicator.base import BaseApplicator


class WTTJApplicator(BaseApplicator):
    name = "wttj"

    async def apply_semi_auto(self, application: Application) -> ApplicationStatus:
        """
        Mode semi-auto pour WTTJ:
        1. Ouvre la page de l'offre
        2. Clique sur "Postuler"
        3. Pré-remplit le formulaire
        4. Attend validation humaine
        """
        page = await self._new_page(headless=False)

        try:
            url = application.job.url
            logger.info(f"[wttj] Ouverture: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay(2, 4)

            # Cookie banner
            try:
                cookie_btn = await page.query_selector(
                    "button:has-text('Tout accepter'), "
                    "button[data-testid='cookie-consent-accept-all']"
                )
                if cookie_btn:
                    await cookie_btn.click()
                    await self._human_delay(1, 2)
            except Exception:
                pass

            # Bouton Postuler
            apply_btn = await page.query_selector(
                "a[data-testid='job-section-apply-cta'], "
                "button:has-text('Postuler'), "
                "a:has-text('Postuler')"
            )

            if apply_btn:
                await apply_btn.click()
                await self._human_delay(2, 4)

                # Pré-remplir les champs
                await self._prefill_form(page)

                # Upload CV
                await self._upload_cv(page)

            logger.info(
                "╔══════════════════════════════════════════════════╗\n"
                "║  🖐️  SEMI-AUTO: Le navigateur est ouvert.       ║\n"
                "║  Vérifie et valide la candidature manuellement. ║\n"
                "║  Appuie sur Entrée dans le terminal quand c'est ║\n"
                "║  fait (ou tape 'skip' pour passer).             ║\n"
                "╚══════════════════════════════════════════════════╝"
            )

            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "[wttj] Candidature envoyée ? (Entrée=oui / skip=non): "
            )

            if user_input.strip().lower() == "skip":
                logger.info("[wttj] Candidature passée par l'utilisateur")
                return ApplicationStatus.READY
            else:
                application.applied_at = datetime.now()
                logger.info(f"[wttj] Candidature confirmée: {application.job.title}")
                return ApplicationStatus.APPLIED

        except Exception as e:
            logger.error(f"[wttj] Erreur semi-auto: {e}")
            return ApplicationStatus.FAILED
        finally:
            await page.close()

    async def apply_full_auto(self, application: Application) -> ApplicationStatus:
        """
        Mode full-auto pour WTTJ.
        WTTJ requiert souvent un compte → plus complexe.
        """
        page = await self._new_page(headless=True)

        try:
            url = application.job.url
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay()

            # Cookie
            try:
                cookie_btn = await page.query_selector("button:has-text('Tout accepter')")
                if cookie_btn:
                    await cookie_btn.click()
                    await self._human_delay(1, 2)
            except Exception:
                pass

            # Bouton Postuler
            apply_btn = await page.query_selector(
                "a[data-testid='job-section-apply-cta'], "
                "button:has-text('Postuler'), "
                "a:has-text('Postuler')"
            )

            if not apply_btn:
                logger.warning(f"[wttj] Pas de bouton postuler: {url}")
                return ApplicationStatus.FAILED

            await apply_btn.click()
            await self._human_delay(2, 5)

            # Pré-remplir
            await self._prefill_form(page)

            # Upload CV
            await self._upload_cv(page)
            await self._human_delay(1, 3)

            # Soumettre
            submit_btn = await page.query_selector(
                "button[type='submit'], "
                "button:has-text('Envoyer'), "
                "button:has-text('Postuler')"
            )

            if submit_btn:
                await submit_btn.click()
                await self._human_delay(3, 6)

                # Vérifier succès
                success = await page.query_selector(
                    "div:has-text('Candidature envoyée'), "
                    "div:has-text('Merci'), "
                    "h2:has-text('envoyée')"
                )
                if success:
                    application.applied_at = datetime.now()
                    logger.info(f"[wttj] ✅ Candidature envoyée: {application.job.title}")
                    return ApplicationStatus.APPLIED

            logger.warning(f"[wttj] Soumission échouée ou incertaine")
            return ApplicationStatus.FAILED

        except Exception as e:
            logger.error(f"[wttj] Erreur full-auto: {e}")
            return ApplicationStatus.FAILED
        finally:
            await page.close()

    async def _prefill_form(self, page):
        """Pré-remplit le formulaire WTTJ."""
        identity = self.profile.get("identite", {})
        responses = self.profile.get("reponses_formulaire", {})

        # Prénom
        await self._fill_field(
            page,
            'input[name*="firstname" i], input[name*="first_name" i], input[placeholder*="prénom" i]',
            identity.get("prenom", ""),
        )

        # Nom
        await self._fill_field(
            page,
            'input[name*="lastname" i], input[name*="last_name" i], input[placeholder*="nom" i]',
            identity.get("nom", ""),
        )

        # Email
        await self._fill_field(
            page,
            'input[type="email"], input[name*="email" i]',
            identity.get("email", ""),
        )

        # Téléphone
        await self._fill_field(
            page,
            'input[type="tel"], input[name*="phone" i]',
            identity.get("telephone", ""),
        )

        # LinkedIn
        linkedin = self.profile.get("liens", {}).get("linkedin", "")
        if linkedin:
            await self._fill_field(
                page,
                'input[name*="linkedin" i], input[placeholder*="linkedin" i]',
                linkedin,
            )

        # Portfolio / GitHub
        github = self.profile.get("liens", {}).get("github", "")
        if github:
            await self._fill_field(
                page,
                'input[name*="portfolio" i], input[name*="website" i], input[placeholder*="portfolio" i]',
                github,
            )

        logger.debug("[wttj] Formulaire pré-rempli")
