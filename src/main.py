"""
Point d'entrée principal du Job Agent.
Usage:
    python -m src.main              # Pipeline complet (scrape + match + postuler)
    python -m src.main --preview    # Scrape + match uniquement (sans postuler)
"""

import asyncio
from src.agent.orchestrator import main


if __name__ == "__main__":
    asyncio.run(main())
