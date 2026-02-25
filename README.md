# Job Agent 🤖

Agent IA de candidature automatique sur **Indeed** et **Welcome to the Jungle**.

## Architecture

```
Job_Agent/
├── config/
│   ├── criteria.yaml      # Tes critères de recherche
│   └── profile.yaml       # Ton profil (nom, email, CV, compétences)
├── src/
│   ├── scrapers/           # Scraping Indeed + WTTJ
│   │   ├── base.py         # Classe de base (anti-détection)
│   │   ├── indeed.py       # Scraper Indeed
│   │   └── wttj.py         # Scraper WTTJ
│   ├── matching/
│   │   └── engine.py       # Filtre + score les offres selon tes critères
│   ├── applicator/         # Module de candidature
│   │   ├── base.py         # Base (form filling, CV upload)
│   │   ├── indeed.py       # Postule sur Indeed
│   │   └── wttj.py         # Postule sur WTTJ
│   ├── tracker/
│   │   └── tracker.py      # Suivi candidatures (SQLite)
│   ├── agent/
│   │   └── orchestrator.py # Agent principal : scrape → match → postule → track
│   ├── models.py           # Modèles de données (Pydantic)
│   ├── config.py           # Configuration centralisée
│   └── main.py             # Point d'entrée CLI
├── api/
│   └── app.py              # API FastAPI pour piloter l'agent
├── cv/                     # Mets ton CV ici (PDF)
├── requirements.txt
└── .env.example
```

## Installation

```bash
# Créer un environnement virtuel
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Installer les dépendances
pip install -r requirements.txt

# Installer Playwright
playwright install chromium

# Copier la config
copy .env.example .env
```

## Configuration

### 1. Critères de recherche (`config/criteria.yaml`)

Modifie ce fichier pour définir :
- **Mots-clés** : les postes que tu cherches
- **Localisation** : villes + rayon
- **Type de contrat** : CDI, CDD...
- **Remote** : full, partiel, aucun
- **Salaire minimum**
- **Expérience max demandée**

### 2. Profil (`config/profile.yaml`)

Remplis avec tes infos personnelles :
- Identité (nom, email, téléphone)
- Liens (LinkedIn, GitHub)
- Compétences
- Réponses pré-remplies pour les formulaires

### 3. CV

Place ton CV en PDF dans le dossier `cv/` et mets à jour le chemin dans `config/profile.yaml`.

## Utilisation

### Mode CLI

```bash
# Mode preview : scrape + filtre sans postuler
python -m src.main --preview

# Pipeline complet : scrape + filtre + postule (semi-auto par défaut)
python -m src.main
```

### Mode API

```bash
# Lancer le serveur
uvicorn api.app:app --reload --port 8000
```

Endpoints disponibles :
| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/` | Status de l'agent |
| POST | `/agent/run` | Lancer le pipeline |
| GET | `/agent/status` | L'agent tourne-t-il ? |
| GET | `/applications` | Lister les candidatures |
| GET | `/applications/stats` | Statistiques |
| PATCH | `/applications/{id}` | Mettre à jour un statut |
| GET | `/criteria` | Voir les critères |
| GET | `/profile` | Voir le profil (masqué) |

## Modes de candidature

### Semi-auto (recommandé)
1. L'agent scrape les offres
2. Filtre selon tes critères
3. Ouvre le navigateur sur l'offre
4. Pré-remplit le formulaire
5. **Tu valides manuellement**

### Full-auto (⚠️ risqué)
1. L'agent fait tout automatiquement
2. Plus rapide, mais détectable
3. Fonctionne mieux sur les "Easy Apply"

> Pour changer de mode, modifie `APPLICATION_MODE` dans `.env`

## Scoring des offres

Chaque offre reçoit un score sur 100 :
| Critère | Points |
|---------|--------|
| Mots-clés | 0-30 |
| Localisation | 0-20 |
| Type de contrat | 0-15 |
| Remote | 0-15 |
| Salaire | 0-10 |
| Expérience | 0-5 |
| Fraîcheur | 0-5 |

Seuil de matching : **50/100**

## Stack technique

- **Python 3.11+**
- **Playwright** — scraping + automation web (anti-détection)
- **Pydantic** — validation des données
- **SQLite** — tracking des candidatures
- **FastAPI** — API HTTP
- **Loguru** — logging
