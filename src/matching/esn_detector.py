"""
Détection du type d'entreprise : ESN (société de service/conseil) vs Client final (direct).

Utilise :
1. Une base de noms d'ESN connues en France
2. Des mots-clés typiques dans le nom ou la description de l'entreprise
"""

from src.models import CompanyType

# ──────────────────────────────────────────────────────────────
# BASE D'ESN CONNUES EN FRANCE (noms normalisés en minuscules)
# ──────────────────────────────────────────────────────────────
ESN_COMPANIES: set[str] = {
    # ── Tier 1 : Grandes ESN internationales ──
    "accenture",
    "capgemini",
    "sopra steria",
    "atos",
    "cgi",
    "cognizant",
    "tcs", "tata consultancy",
    "infosys",
    "wipro",
    "hcl",
    "dxc technology", "dxc",
    "ibm consulting",
    "deloitte",
    "kpmg",
    "pwc", "pricewaterhousecoopers",
    "ey", "ernst & young", "ernst and young",
    "mckinsey",
    "boston consulting", "bcg",
    "bain",

    # ── Tier 2 : ESN françaises majeures ──
    "alten",
    "altran",
    "akka", "akka technologies",
    "assystem",
    "aubay",
    "ausy",
    "devoteam",
    "gfi informatique", "gfi",
    "inetum",
    "modis",
    "neurones",
    "open", "open groupe",
    "sii",
    "sogeti",
    "steria",
    "sword",
    "talan",
    "thales digital", "thales sis",
    "wavestone",
    "onepoint",
    "mc2i",
    "mc2i groupe",
    "sia partners",
    "bearing point", "bearingpoint",

    # ── Tier 3 : ESN / cabinets spécialisés data/tech ──
    "arolla",
    "beyondsoft",
    "business & decision",
    "catalyst",
    "celencia",
    "citech",
    "cloudreach",
    "consort",
    "consort nt",
    "davidson", "davidson consulting",
    "econocom",
    "extia",
    "freelance.com",
    "hardis", "hardis group",
    "headmind", "headmind partners",
    "helpline",
    "infeeny",
    "input", "input consulting",
    "ippon", "ippon technologies",
    "keyrus",
    "klee", "klee group",
    "logica",
    "micropole",
    "n-allo",
    "niji",
    "novencia",
    "octo", "octo technology",
    "quantmetry",
    "revolve",
    "scalian",
    "sfeir",
    "smile",
    "sqli",
    "synaltic",
    "synapse",
    "ten consulting",
    "viseo",
    "wescale",
    "westpoint",
    "xebia",
    "zenika",

    # ── Cabinets / sociétés de conseil classiques ──
    "adneom",
    "apside",
    "clever age",
    "commerce",
    "crédit mutuel arkéa", # DSI interne mais souvent ESN-like
    "datavalue", "datavalue consulting",
    "digora",
    "groupe hisi",
    "harness",
    "inextenso",
    "inside group",
    "kantar",
    "lojelis",
    "magellan", "magellan consulting",
    "manpower",
    "mylan",
    "néosoft", "neosoft",
    "nexworld",
    "norsys",
    "oxalide",
    "ozitem",
    "pentalog",
    "pentasafe",
    "proginov",
    "quorsus",
    "saegus",
    "solutec",
    "suricog",
    "teamwork",
    "tessi",
    "the tribe",
    "twelve consulting",
    "umantis",
    "wemanity",
    "yotta",

    # ── ESN / intérim tech ──
    "adecco",
    "hays",
    "michael page",
    "page personnel",
    "randstad", "randstad digital",
    "robert half",
    "robert walters",
    "spring",
    "talent.io",
    "urban linker",
    "hired",
    "free-work",
    "kicklox",
    "malt",
    "comet",
    "lewagon",
    "sthree",
    "computer futures",
    "jefferson frank",
    "nigel frank",
    "anderson frank",
    "progressive",
    "blue coding",
    "experis",
    "manpowergroup",
    "gi group",
}

# ──────────────────────────────────────────────────────────────
# MOTS-CLÉS typiques des ESN dans le nom ou la description
# ──────────────────────────────────────────────────────────────
ESN_KEYWORDS: list[str] = [
    "esn",
    "société de service",
    "societe de service",
    "société de conseil",
    "societe de conseil",
    "cabinet de conseil",
    "consulting",
    "consultancy",
    "services numériques",
    "services numeriques",
    "services informatiques",
    "intégrateur",
    "integrateur",
    "prestataire",
    "body shopping",
    "régie",
    "regie",
    "infogérance",
    "infogerance",
    "outsourcing",
    "managed services",
    "staffing",
    "placement",
    "missions chez nos clients",
    "chez le client",
    "nos clients grands comptes",
    "interventions chez",
    "missions en clientèle",
    "rejoindre nos équipes de consultants",
    "consultant data",
    "consultant technique",
    "consultant fonctionnel",
]


def detect_company_type(company_name: str, description: str = "") -> CompanyType:
    """
    Détecte si une entreprise est une ESN ou un client final.

    Args:
        company_name: Nom de l'entreprise
        description: Description de l'offre (optionnel)

    Returns:
        CompanyType.ESN, CompanyType.DIRECT, ou CompanyType.UNKNOWN
    """
    name_lower = company_name.lower().strip()
    desc_lower = description.lower()

    # 1. Vérifier le nom contre la base d'ESN connues
    for esn in ESN_COMPANIES:
        # Match exact ou le nom contient l'ESN (ex: "Capgemini Engineering" match "capgemini")
        if esn in name_lower or name_lower in esn:
            return CompanyType.ESN

    # 2. Vérifier les mots-clés ESN dans le nom de l'entreprise
    for kw in ESN_KEYWORDS[:10]:  # Les plus discriminants
        if kw in name_lower:
            return CompanyType.ESN

    # 3. Vérifier les mots-clés ESN dans la description
    esn_signals = 0
    for kw in ESN_KEYWORDS:
        if kw in desc_lower:
            esn_signals += 1

    # Si 2+ signaux ESN dans la description → probablement une ESN
    if esn_signals >= 2:
        return CompanyType.ESN

    # 4. Si un seul signal + description courte → ESN probable
    if esn_signals == 1 and len(desc_lower) < 500:
        return CompanyType.ESN

    # 5. Pas de signal ESN → on considère que c'est du direct
    # (sauf si la description est vide, auquel cas on ne sait pas)
    if not description.strip():
        return CompanyType.UNKNOWN

    return CompanyType.DIRECT


def get_company_type_label(company_type: CompanyType) -> str:
    """Retourne un label lisible pour le type d'entreprise."""
    labels = {
        CompanyType.ESN: "🏢 ESN/Service",
        CompanyType.DIRECT: "🏠 Client Final",
        CompanyType.UNKNOWN: "❓ Non déterminé",
    }
    return labels.get(company_type, "❓ Non déterminé")
