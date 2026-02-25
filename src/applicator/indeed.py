"""
Module de candidature pour Indeed.
"""

import asyncio
from datetime import datetime

from loguru import logger

from src.models import Application, ApplicationStatus
from src.applicator.base import BaseApplicator


class IndeedApplicator(BaseApplicator):
    name = "indeed"

    async def apply_semi_auto(self, application: Application) -> ApplicationStatus:
        """
        Mode semi-auto pour Indeed:
        1. Ouvre la page de l'offre dans un navigateur visible
        2. Pré-remplit les champs si possible
        3. Attend que l'utilisateur valide manuellement
        """
        page = await self._new_page(headless=False)

        try:
            url = application.job.url
            logger.info(f"[indeed] Ouverture: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay(1, 3)

            # Cherche le bouton "Postuler"
            apply_btn = await page.query_selector(
                "button#indeedApplyButton, "
                "button[data-testid='apply-button'], "
                "a.jobsearch-IndeedApplyButton-newDesign, "
                "button:has-text('Postuler'), "
                "a:has-text('Postuler')"
            )

            if apply_btn:
                await apply_btn.click()
                await self._human_delay(2, 4)

                # Tenter de pré-remplir les champs
                await self._prefill_form(page)

            # Notification à l'utilisateur
            logger.info(
                "╔══════════════════════════════════════════════════╗\n"
                "║  🖐️  SEMI-AUTO: Le navigateur est ouvert.       ║\n"
                "║  Vérifie et valide la candidature manuellement. ║\n"
                "║  Appuie sur Entrée dans le terminal quand c'est ║\n"
                "║  fait (ou tape 'skip' pour passer).             ║\n"
                "╚══════════════════════════════════════════════════╝"
            )

            # Attendre confirmation utilisateur
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "[indeed] Candidature envoyée ? (Entrée=oui / skip=non): "
            )

            if user_input.strip().lower() == "skip":
                logger.info("[indeed] Candidature passée par l'utilisateur")
                return ApplicationStatus.READY
            else:
                application.applied_at = datetime.now()
                logger.info(f"[indeed] Candidature confirmée: {application.job.title}")
                return ApplicationStatus.APPLIED

        except Exception as e:
            logger.error(f"[indeed] Erreur semi-auto: {e}")
            return ApplicationStatus.FAILED
        finally:
            await page.close()

    async def apply_full_auto(self, application: Application) -> ApplicationStatus:
        """
        Mode full-auto pour Indeed:
        Tente de postuler automatiquement ("Easy Apply").
        ⚠️ Fonctionnel uniquement sur les offres avec candidature simplifiée.
        """
        page = await self._new_page(headless=True)

        try:
            url = application.job.url
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay()

            # Bouton Postuler
            apply_btn = await page.query_selector(
                "button#indeedApplyButton, "
                "button[data-testid='apply-button'], "
                "button:has-text('Postuler')"
            )

            if not apply_btn:
                logger.warning(f"[indeed] Pas de bouton postuler trouvé: {url}")
                return ApplicationStatus.FAILED

            await apply_btn.click()
            await self._human_delay(2, 5)

            # Pré-remplir
            await self._prefill_form(page)

            # Upload CV
            await self._upload_cv(page)
            await self._human_delay(1, 3)

            # Chercher bouton de soumission
            submit_btn = await page.query_selector(
                "button[type='submit'], "
                "button:has-text('Envoyer'), "
                "button:has-text('Soumettre'), "
                "button:has-text('Submit')"
            )

            if submit_btn:
                await submit_btn.click()
                await self._human_delay(3, 6)

                # Vérifier succès
                success = await page.query_selector(
                    "div:has-text('candidature envoyée'), "
                    "div:has-text('application submitted'), "
                    "h1:has-text('Merci')"
                )
                if success:
                    application.applied_at = datetime.now()
                    logger.info(f"[indeed] ✅ Candidature envoyée: {application.job.title}")
                    return ApplicationStatus.APPLIED
                else:
                    logger.warning(f"[indeed] ⚠️ Soumission incertaine: {application.job.title}")
                    return ApplicationStatus.APPLIED  # Optimiste

            logger.warning(f"[indeed] Pas de bouton submit trouvé")
            return ApplicationStatus.FAILED

        except Exception as e:
            logger.error(f"[indeed] Erreur full-auto: {e}")
            return ApplicationStatus.FAILED
        finally:
            await page.close()

    async def _prefill_form(self, page):
        """Pré-remplit les champs du formulaire Indeed."""
        identity = self.profile.get("identite", {})
        responses = self.profile.get("reponses_formulaire", {})

        # Nom / Prénom
        await self._fill_field(page, 'input[name*="name" i]', f"{identity.get('prenom', '')} {identity.get('nom', '')}")
        await self._fill_field(page, 'input[name*="first" i]', identity.get("prenom", ""))
        await self._fill_field(page, 'input[name*="last" i]', identity.get("nom", ""))

        # Email
        await self._fill_field(page, 'input[type="email"], input[name*="email" i]', identity.get("email", ""))

        # Téléphone
        await self._fill_field(page, 'input[type="tel"], input[name*="phone" i]', identity.get("telephone", ""))

        # Ville
        await self._fill_field(page, 'input[name*="location" i], input[name*="city" i]', identity.get("ville", ""))

        logger.debug("[indeed] Formulaire pré-rempli")
