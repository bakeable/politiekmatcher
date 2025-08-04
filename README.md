# PolitiekMatcher

**Transparante politieke analyse via AI** - Een open-source platform dat Nederlandse burgers helpt hun politieke voorkeur te begrijpen via AI-gestuurde analyse.

## 🎯 Projectdoel

PolitiekMatcher biedt objectieve, transparante politieke analyse door gebruikersmeningen te koppelen aan Nederlandse politieke partijen. Met geavanceerde AI en machine learning analyseert het platform politieke stellingen op zeven belangrijke dimensies, zodat burgers weloverwogen stemkeuzes kunnen maken.

### Belangrijkste functies

- **🤖 AI-gestuurde opinieanalyse**: Classificeert automatisch gebruikersmeningen met fijn-afgestelde taalmodellen
- **📊 Multidimensionale politieke mapping**: Analyse op zeven dimensies, waaronder economisch, sociaal, milieu en institutioneel
- **🔍 Transparant matching-algoritme**: Volledig inzicht in hoe partijmatches worden berekend
- **📚 Uitgebreide partijdata**: Analyse van officiële verkiezingsprogramma’s en partijstandpunten
- **🎨 Moderne webinterface**: Gebouwd met React, TypeScript en GraphQL

## 🏗️ Architectuur

Het platform bestaat uit:

- **Frontend**: React + TypeScript + Apollo GraphQL
- **Backend**: Django + Strawberry GraphQL
- **AI/ML**: Aangepaste fijn-afgestelde transformer modellen + OpenAI GPT-integratie
- **Database**: PostgreSQL met pgvector voor semantisch zoeken
- **Taakqueue**: Celery + Redis voor achtergrondverwerking

## 📋 Vereisten

- Python 3.11 of 3.12
- Poetry (dependency management)
- PostgreSQL 14+
- Redis
- Node.js 18+ (voor frontend-ontwikkeling)

## 🚀 Snel starten

### 1. Repository klonen

```bash
git clone https://github.com/yourusername/politiekmatcher.git
cd politiekmatcher
```

### 2. Python-omgeving instellen

```bash
# Installeer Poetry als je dat nog niet hebt gedaan
curl -sSL https://install.python-poetry.org | python3 -

# Installeer afhankelijkheden
poetry install

# Activeer virtuele omgeving
poetry shell
```

### 3. Omgeving configureren

```bash
# Kopieer sjabloon voor omgeving
cp .env.example .env

# Bewerk .env met jouw configuratie:
# - Database-instellingen
# - OpenAI API-sleutel
# - Redis-configuratie
# - Geheime sleutels
```

### 4. Database instellen

```bash
# Start PostgreSQL en Redis
brew services start postgresql
brew services start redis

# Maak database aan
createdb politiekmatcher

# Voer migraties uit
python manage.py migrate

# Laad initiële data (optioneel)
python manage.py loaddata initial_data.json
```

### 5. ML-modellen downloaden

```bash
# Download vooraf getrainde modellen
python manage.py download_models

# Of train je eigen modellen (vereist veel rekenkracht)
python manage.py train_models
```

### 6. Ontwikkelserver starten

```bash
# Start Django ontwikkelserver
python manage.py runserver

# Start Celery worker in een andere terminal
celery -A politiekmatcher worker -l info

# Start Celery beat (voor geplande taken)
celery -A politiekmatcher beat -l info
```

De API is beschikbaar op `http://localhost:8000/graphql/`

## 🔧 Ontwikkelomgeving

### Ontwikkelafhankelijkheden installeren

```bash
poetry install --with dev
```

### Codekwaliteit tools

```bash
# Code formatteren
black .

# Code linten
ruff check .

# Type checking
mypy .

# Tests uitvoeren
pytest
```

### Pre-commit hooks

```bash
# Installeer pre-commit
pip install pre-commit

# Stel git hooks in
pre-commit install
```

## 📚 Documentatie

Uitgebreide documentatie is beschikbaar in de [`docs/`](docs/) map:

- **[Systeemarchitectuur](docs/system_architecture.md)** - Overzicht van systeemontwerp en datastromen
- **[Opinieclassificatie](docs/opinion_classification.md)** - Hoe gebruikersmeningen worden geclassificeerd
- **[Matching-algoritme](docs/matching_algorithm.md)** - Volledige transparantie van het matchingproces
- **[Politieke dimensies](docs/political_dimensions_finetuning.md)** - Zevendimensionale politieke analyse
- **[OpenAI-integratie](docs/openai_integration.md)** - AI-gestuurde uitleg en analyse
- **[Databronnen](docs/data_sources_and_processing.md)** - Verzameling en verwerking van politieke content

## 🗂️ Projectstructuur

```
politiekmatcher/
├── apps/                    # Django-applicaties
│   ├── api/                # GraphQL API-definities
│   ├── chat/               # Chatinterface-logica
│   ├── content/            # Politieke contentmodellen
│   ├── profiles/           # Gebruikersprofielen en matching
│   ├── scraping/           # Dataverzamelingstools
│   └── utils/              # Gedeelde utilities
├── docs/                   # Uitgebreide documentatie
├── models/                 # ML-modellen en trainingsdata
├── scraped_content/        # Partijprogramma’s en data
├── tests/                  # Test suite
└── politiekmatcher/        # Django projectinstellingen
```

## 🤝 Bijdragen

Bijdragen zijn welkom! Zie onze [bijdrage-richtlijnen](CONTRIBUTING.md) voor details.

### Ontwikkelworkflow

1. Fork de repository
2. Maak een feature branch (`git checkout -b feature/amazing-feature`)
3. Breng je wijzigingen aan
4. Voer tests uit (`pytest`)
5. Commit je wijzigingen (`git commit -m 'Add amazing feature'`)
6. Push naar de branch (`git push origin feature/amazing-feature`)
7. Open een Pull Request

## 📊 Transparantiebelofte

PolitiekMatcher streeft naar volledige transparantie in politieke analyse:

- **Open Source**: Alle code is openbaar beschikbaar
- **Gedocumenteerde algoritmes**: Elke stap van het matchingproces is gedocumenteerd
- **Traceerbare databronnen**: Alle partijstandpunten verwijzen naar officiële bronnen
- **Bias-monitoring**: Regelmatige audits van AI-uitvoer op politieke bias
- **Expertvalidatie**: Menselijke experts beoordelen AI-geclassificeerde politieke stellingen

## 📄 Licentie

Dit project is gelicentieerd onder de MIT-licentie - zie het [LICENSE](LICENSE) bestand voor details.

## 🙋‍♀️ Support

- **Documentatie**: Zie de [`docs/`](docs/) map
- **Issues**: Meld bugs via [GitHub Issues](https://github.com/yourusername/politiekmatcher/issues)
- **Discussies**: Doe mee aan gesprekken in [GitHub Discussions](https://github.com/yourusername/politiekmatcher/discussions)

## 🏛️ Politieke neutraliteit

PolitiekMatcher is ontworpen om politiek neutraal te zijn. Onze algoritmes en AI-modellen zijn getraind om objectieve analyses te bieden zonder voorkeur voor een bepaalde politieke ideologie. We monitoren continu op bias en verwelkomen toezicht vanuit de community.

---

**Gemaakt met ❤️ voor de Nederlandse democratie**
