"""
Système de suivi des candidatures (SQLite).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.config import ROOT_DIR
from src.models import Application, ApplicationStatus, JobOffer, JobSource


DB_PATH = ROOT_DIR / "job_agent.db"


class ApplicationTracker:
    """Gère le suivi des candidatures dans une base SQLite."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _init_db(self):
        """Crée les tables si elles n'existent pas."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    url TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    salary_min INTEGER,
                    salary_max INTEGER,
                    contract_type TEXT DEFAULT 'Inconnu',
                    remote TEXT DEFAULT 'inconnu',
                    experience_required INTEGER,
                    date_posted TEXT,
                    date_scraped TEXT NOT NULL,
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    match_score REAL DEFAULT 0,
                    match_details TEXT DEFAULT '{}',
                    applied_at TEXT,
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (job_id) REFERENCES jobs(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)
            """)
            conn.commit()
        logger.info(f"[tracker] Base de données initialisée: {self.db_path}")

    def save_job(self, offer: JobOffer) -> int:
        """Sauvegarde une offre. Retourne l'id (existant ou nouveau)."""
        with sqlite3.connect(self.db_path) as conn:
            # Vérifier si déjà existant
            row = conn.execute(
                "SELECT id FROM jobs WHERE url = ?", (offer.url,)
            ).fetchone()

            if row:
                return row[0]

            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    title, company, location, description, url, source,
                    salary_min, salary_max, contract_type, remote,
                    experience_required, date_posted, date_scraped, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    offer.title,
                    offer.company,
                    offer.location,
                    offer.description,
                    offer.url,
                    offer.source.value,
                    offer.salary_min,
                    offer.salary_max,
                    offer.contract_type.value,
                    offer.remote.value,
                    offer.experience_required,
                    str(offer.date_posted) if offer.date_posted else None,
                    str(offer.date_scraped),
                    json.dumps(offer.tags),
                ),
            )
            conn.commit()
            logger.debug(f"[tracker] Job sauvegardé: {offer.title} (id={cursor.lastrowid})")
            return cursor.lastrowid

    def save_application(self, application: Application) -> int:
        """Sauvegarde une candidature."""
        job_id = self.save_job(application.job)

        with sqlite3.connect(self.db_path) as conn:
            # Vérifier si déjà candidaté
            row = conn.execute(
                "SELECT id FROM applications WHERE job_id = ?", (job_id,)
            ).fetchone()

            if row:
                # Mettre à jour
                conn.execute(
                    """
                    UPDATE applications
                    SET status = ?, match_score = ?, match_details = ?,
                        applied_at = ?, notes = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        application.status.value,
                        application.match_score,
                        json.dumps(application.match_details),
                        str(application.applied_at) if application.applied_at else None,
                        application.notes,
                        str(datetime.now()),
                        row[0],
                    ),
                )
                conn.commit()
                return row[0]

            cursor = conn.execute(
                """
                INSERT INTO applications (
                    job_id, status, match_score, match_details,
                    applied_at, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    application.status.value,
                    application.match_score,
                    json.dumps(application.match_details),
                    str(application.applied_at) if application.applied_at else None,
                    application.notes,
                    str(datetime.now()),
                    str(datetime.now()),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_status(self, application_id: int, status: ApplicationStatus):
        """Met à jour le statut d'une candidature."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE applications SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, str(datetime.now()), application_id),
            )
            conn.commit()

    def get_all_applications(self, status: str | None = None) -> list[dict]:
        """Récupère toutes les candidatures avec infos du job."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT a.*, j.title, j.company, j.location, j.url, j.source,
                       j.salary_min, j.salary_max, j.contract_type, j.remote
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
            """
            params = []
            if status:
                query += " WHERE a.status = ?"
                params.append(status)
            query += " ORDER BY a.match_score DESC"

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """Retourne des statistiques sur les candidatures."""
        with sqlite3.connect(self.db_path) as conn:
            total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            total_apps = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]

            status_counts = {}
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM applications GROUP BY status"
            ).fetchall()
            for row in rows:
                status_counts[row[0]] = row[1]

            avg_score = conn.execute(
                "SELECT AVG(match_score) FROM applications WHERE status != 'rejected'"
            ).fetchone()[0]

            return {
                "total_jobs_scraped": total_jobs,
                "total_applications": total_apps,
                "by_status": status_counts,
                "avg_match_score": round(avg_score or 0, 1),
            }

    def is_already_applied(self, url: str) -> bool:
        """Vérifie si on a déjà postulé à cette offre."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT a.status FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE j.url = ? AND a.status = 'applied'
                """,
                (url,),
            ).fetchone()
            return row is not None
