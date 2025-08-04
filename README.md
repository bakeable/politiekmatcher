# PolitiekMatcher

**Transparante politieke analyse via AI** - An open-source platform that helps Dutch citizens understand their political alignment through AI-powered analysis.

## 🎯 Project Goal

PolitiekMatcher provides objective, transparent political analysis by matching user opinions with Dutch political parties. Using advanced AI and machine learning, the platform analyzes political statements across seven key dimensions to help citizens make informed voting decisions.

### Key Features

- **🤖 AI-Powered Opinion Analysis**: Automatically classifies user opinions using fine-tuned language models
- **📊 Multi-Dimensional Political Mapping**: Seven-dimensional analysis framework covering economic, social, environmental, and institutional positions
- **🔍 Transparent Matching Algorithm**: Complete visibility into how party matches are calculated
- **📚 Comprehensive Party Data**: Analysis of official election programs and party positions
- **💬 Interactive Chat Interface**: Natural conversation flow for political discussion
- **🎨 Modern Web Interface**: Built with React, TypeScript, and GraphQL

## 🏗️ Architecture

The platform consists of:

- **Frontend**: React + TypeScript + Apollo GraphQL
- **Backend**: Django + Strawberry GraphQL
- **AI/ML**: Custom fine-tuned transformer models + OpenAI GPT integration
- **Database**: PostgreSQL with pgvector for semantic search
- **Task Queue**: Celery + Redis for background processing

## 📋 Prerequisites

- Python 3.11 or 3.12
- Poetry (dependency management)
- PostgreSQL 14+
- Redis
- Node.js 18+ (for frontend development)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/politiekmatcher.git
cd politiekmatcher
```

### 2. Set Up Python Environment

```bash
# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration:
# - Database settings
# - OpenAI API key
# - Redis configuration
# - Secret keys
```

### 4. Set Up Database

```bash
# Start PostgreSQL and Redis
brew services start postgresql
brew services start redis

# Create database
createdb politiekmatcher

# Run migrations
python manage.py migrate

# Load initial data (optional)
python manage.py loaddata initial_data.json
```

### 5. Download ML Models

```bash
# Download pre-trained models
python manage.py download_models

# Or train your own models (requires significant compute)
python manage.py train_models
```

### 6. Start Development Server

```bash
# Start Django development server
python manage.py runserver

# In another terminal, start Celery worker
celery -A politiekmatcher worker -l info

# Start Celery beat (for scheduled tasks)
celery -A politiekmatcher beat -l info
```

The API will be available at `http://localhost:8000/graphql/`

## 🔧 Development Setup

### Install Development Dependencies

```bash
poetry install --with dev
```

### Code Quality Tools

```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy .

# Run tests
pytest
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Set up git hooks
pre-commit install
```

## 📚 Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- **[System Architecture](docs/system_architecture.md)** - Overall system design and data flow
- **[Opinion Classification](docs/opinion_classification.md)** - How user opinions are classified
- **[Matching Algorithm](docs/matching_algorithm.md)** - Complete transparency of the matching process
- **[Political Dimensions](docs/political_dimensions_finetuning.md)** - Seven-dimensional political analysis
- **[OpenAI Integration](docs/openai_integration.md)** - AI-powered explanations and analysis
- **[Data Sources](docs/data_sources_and_processing.md)** - Political content collection and processing

## 🗂️ Project Structure

```
politiekmatcher/
├── apps/                    # Django applications
│   ├── api/                # GraphQL API definitions
│   ├── chat/               # Chat interface logic
│   ├── content/            # Political content models
│   ├── profiles/           # User profiles and matching
│   ├── scraping/           # Data collection tools
│   └── utils/              # Shared utilities
├── docs/                   # Comprehensive documentation
├── models/                 # ML models and training data
├── scraped_content/        # Political party programs and data
├── tests/                  # Test suite
└── politiekmatcher/        # Django project settings
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📊 Transparency Commitment

PolitiekMatcher is committed to complete transparency in political analysis:

- **Open Source**: All code is publicly available
- **Documented Algorithms**: Every step of the matching process is documented
- **Traceable Data Sources**: All party positions link back to official sources
- **Bias Monitoring**: Regular audits of AI model outputs for political bias
- **Expert Validation**: Human experts review AI-generated political classifications

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙋‍♀️ Support

- **Documentation**: Check the [`docs/`](docs/) directory
- **Issues**: Report bugs on [GitHub Issues](https://github.com/yourusername/politiekmatcher/issues)
- **Discussions**: Join conversations in [GitHub Discussions](https://github.com/yourusername/politiekmatcher/discussions)

## 🏛️ Political Neutrality

PolitiekMatcher is designed to be politically neutral. Our algorithms and AI models are trained to provide objective analysis without favoring any particular political ideology. We continuously monitor for bias and welcome community oversight.

---

**Made with ❤️ for Dutch democracy**
