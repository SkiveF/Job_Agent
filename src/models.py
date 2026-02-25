"""
Modèles de données pour les offres d'emploi et les candidatures.
"""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class JobSource(str, Enum):
    INDEED = "indeed"
    WTTJ = "wttj"


class ContractType(str, Enum):
    CDI = "CDI"
    CDD = "CDD"
    FREELANCE = "Freelance"
    STAGE = "Stage"
    ALTERNANCE = "Alternance"
    UNKNOWN = "Inconnu"


class RemoteType(str, Enum):
    FULL = "full"
    PARTIAL = "partiel"
    NONE = "aucun"
    UNKNOWN = "inconnu"


class CompanyType(str, Enum):
    """Type d'entreprise : ESN/société de service vs client final."""
    ESN = "esn"                    # Société de service / conseil / ESN
    DIRECT = "direct"              # Client final / entreprise directe
    UNKNOWN = "inconnu"            # Non déterminé


class ApplicationStatus(str, Enum):
    NEW = "new"                    # Offre détectée, pas encore traitée
    MATCHED = "matched"            # Correspond aux critères
    REJECTED = "rejected"          # Ne correspond pas aux critères
    READY = "ready"                # Prêt à postuler (semi-auto)
    APPLIED = "applied"            # Candidature envoyée
    FAILED = "failed"              # Erreur lors de la candidature
    INTERVIEW = "interview"        # Entretien obtenu
    OFFER = "offer"                # Offre reçue
    DECLINED = "declined"          # Refusé par le candidat


class JobOffer(BaseModel):
    """Représente une offre d'emploi scrapée."""
    id: str | None = None
    title: str
    company: str
    location: str
    description: str = ""
    url: str
    source: JobSource
    salary_min: int | None = None
    salary_max: int | None = None
    contract_type: ContractType = ContractType.UNKNOWN
    remote: RemoteType = RemoteType.UNKNOWN
    company_type: CompanyType = CompanyType.UNKNOWN
    experience_required: int | None = None  # Années
    date_posted: datetime | None = None
    date_scraped: datetime = Field(default_factory=datetime.now)
    tags: list[str] = Field(default_factory=list)
    raw_data: dict = Field(default_factory=dict)

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return isinstance(other, JobOffer) and self.url == other.url


class Application(BaseModel):
    """Représente une candidature."""
    id: str | None = None
    job: JobOffer
    status: ApplicationStatus = ApplicationStatus.NEW
    match_score: float = 0.0  # Score 0-100
    match_details: dict = Field(default_factory=dict)
    applied_at: datetime | None = None
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
