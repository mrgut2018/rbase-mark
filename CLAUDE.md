# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Deep Academic Research (deepsearcher) is an academic research assistance system based on RAG (Retrieval-Augmented Generation) technology. The system performs in-depth analysis and summarization of academic literature, supporting both research topic reviews and researcher achievement analysis. It integrates with MySQL for metadata storage and vector databases (Milvus/Oracle) for semantic search.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac

# Install dependencies (editable mode)
pip install -e .
```

### Configuration
```bash
# Use config.rbase.yaml for RBase-specific operations
# Use config.yaml for general DeepSearcher operations

# Configuration files contain:
# - LLM provider settings (OpenAI, DeepSeek, Qwen, etc.)
# - Vector database connection (Milvus/Oracle)
# - MySQL database connection
# - Embedding model configuration
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_milvus.py

# Run with verbose output
pytest -v
```

### Code Quality
```bash
# Format code with ruff (configured in pyproject.toml)
ruff format .

# Lint code
ruff check .

# Fix auto-fixable issues
ruff check --fix .
```

### API Service
```bash
# Start API server directly
python scripts/start_api_server.py

# Or using the service file (production)
sudo systemctl start rbase-api
sudo systemctl status rbase-api
sudo journalctl -u rbase-api -f
```

### Classification Services
```bash
# Task dispatcher (polls auto_task table and creates MNS messages)
python services/task_dispatcher.py --interval 5 --verbose

# Classification service (multi-process worker consuming MNS messages)
python services/classify_service.py --workers 4 --verbose

# As systemd services
sudo systemctl start task-dispatcher
sudo systemctl start classify-service
```

## Architecture

### Core Module Structure

The project follows a modular architecture with clear separation of concerns:

**`deepsearcher/agent/`** - RAG agents and academic processing
- `ClassifyAgent`: Manages article classification workflows with multiple classifier types
- `OverviewRAG`: Generates comprehensive research topic reviews
- `PersonalRAG`: Creates researcher achievement reviews
- `SummaryRAG`: Intelligent literature summarization
- `DiscussAgent`: Interactive academic Q&A with conversation history
- `DeepSearch`: Advanced multi-iteration retrieval agent
- `ChainOfRAG`: Multi-step reasoning for complex queries
- `NaiveRAG`: Basic retrieval-augmented generation
- `AcademicTranslator`: Handles bilingual (EN/CN) academic term translation

**`deepsearcher/llm/`** - LLM provider abstractions
- Unified interface (`BaseLLM`) for multiple providers
- Supported: OpenAI, Anthropic, DeepSeek, Gemini, TogetherAI, SiliconFlow, Azure OpenAI, XAI, Ollama
- Streaming generation support

**`deepsearcher/embedding/`** - Embedding model providers
- Supported: OpenAI, Voyage, Bedrock, SiliconFlow, Milvus
- Unified interface for text vectorization

**`deepsearcher/vector_db/`** - Vector database integrations
- Milvus and Oracle vector database support
- Collection-based organization with routing capabilities

**`deepsearcher/api/`** - FastAPI REST API
- `main.py`: Application initialization and lifespan management
- `routes/`: API endpoint definitions
- `models.py`: Pydantic models for request/response
- `rbase_util/`: Database utilities and helper functions

**`deepsearcher/rbase/`** - RBase data models
- `ai_models.py`: Classifier, ClassifierGroup, ClassifierValue models
- `raw_article.py`: RawArticle model for literature metadata
- `rbase_article.py`: Extended article models
- `terms.py`: Terminology and concept models

**`deepsearcher/loader/`** - Data loading
- `file_loader/`: PDF, JSON, text file loaders
- `web_crawler/`: Crawl4AI, Firecrawl, Jina crawler integrations

### Configuration System

The `Configuration` class (in `configuration.py`) uses a factory pattern:
- Loads YAML config files specifying providers and settings
- `ModuleFactory` dynamically instantiates LLMs, embeddings, vector DBs, etc.
- Global singleton pattern with `init_config()` / `init_rbase_config()` helpers
- Supports multiple LLM roles: `llm`, `reasoning_llm`, `lctx_reasoning_llm` (long context), `writing_llm`

### Database Architecture

**MySQL** - Stores metadata and relational data:
- `raw_article`: Literature metadata (title, DOI, authors, abstract)
- `classifier`, `classifier_group`, `classifier_value`: Classification taxonomy
- `term_tree`, `term_tree_node`, `concept`: Hierarchical terminology system
- `auto_task`, `auto_sub_task`: Asynchronous task management
- `label_raw_article_task*`: Manual labeling workflows
- `vector_db_data_log`: Tracks vector DB operations for integrity

**Vector Database** (Milvus/Oracle):
- Collections organized by embedding model and version
- Stores chunked text embeddings with metadata
- Supports semantic search and similarity ranking
- Collection names follow pattern: `{env}_{project}_{model}_{version}`

### Classification System

The classification system supports three classifier types (defined in `deepsearcher.rbase.ai_models`):

1. **GENERAL_VALUE**: LLM-based text classification using prompts
2. **NAMED_ENTITY**: Named entity matching with optional vector DB lookup
3. **ROUTING**: Multi-level classification routing (in development)

**Classification Workflow:**
1. Load `Classifier` from database by ID or alias
2. Check prerequisites (depends on prior classification results)
3. Execute classification via `ClassifyAgent.classify_article()`
4. For NAMED_ENTITY: optionally search vector DB for candidate values
5. Save results to `raw_article_classifier_result` table
6. Update task status in `auto_sub_task` and `auto_task`

**Asynchronous Task System:**
- `task_dispatcher.py`: Polls `auto_task` table, creates `auto_sub_task` records, sends MNS messages
- `classify_service.py`: Multi-process workers consume MNS messages and execute classifications
- Task types: `AI_GENERAL_CLASSIFY_RAW_ARTICLE`, `AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE`, `AI_SINGLE_CLASSIFY_RAW_ARTICLE`

### Scripts Directory

`scripts/` contains operational tools (see `scripts/README.md` for details):
- **Data integrity**: `check_vector_db_integrity.py`, `query_vector_db_by_id.py`
- **Vector DB creation**: `create_rbase_vector_db.py`, `create_json_vector_db.py`
- **Classification**: `classify_raw_article.py`, `batch_classify_articles.py`, `build_classifier_values.py`
- **Content generation**: `compose_overview_with_rag.py`, `compose_personal_with_rag.py`
- **Data import**: `import_term_tree_nodes.py`, `import_classifiers.py`
- **Labeling**: `export_label_task_result.py`, `batch_export_label_results.py`

## Development Practices

### Adding New LLM Providers

1. Create new file in `deepsearcher/llm/` (e.g., `my_provider.py`)
2. Inherit from `BaseLLM` and implement required methods
3. Update `configuration.py` to support the new provider
4. Add provider config to YAML file

### Working with Classifiers

When modifying classifier logic:
- Core logic is in `deepsearcher/agent/classify_agent.py`
- Prompts are in `deepsearcher/agent/prompts/classify_prompts.py`
- Database models are in `deepsearcher/rbase/ai_models.py`
- Always check prerequisite conditions before classification
- Test with `scripts/classify_raw_article.py` before batch operations

### Vector Database Operations

- Use `check_vector_db_integrity.py` to verify data consistency
- Collection names must match between MySQL `vector_db_data_log` and actual collections
- Always log operations to `vector_db_data_log` for audit trail
- Batch operations should use appropriate batch sizes (default: 1000)

### API Development

- Routes are organized in `deepsearcher/api/routes/`
- Use Pydantic models from `models.py` for validation
- Database utilities are in `deepsearcher/api/rbase_util/`
- Streaming responses use `StreamingResponse` with async generators
- Configuration is accessible via `configuration.config` singleton

### Code Style

- Python 3.10+ required
- Ruff configuration in `pyproject.toml` (line length: 100)
- Use type hints where possible
- Follow existing patterns for logging (use `deepsearcher.tools.log`)

## Common Workflows

### Adding a New Classifier

1. Insert classifier definition in `classifier` table
2. Create classifier values with `scripts/build_classifier_values.py`
3. Test single article: `scripts/classify_raw_article.py --classifier_id X --raw_article_id Y`
4. For batch: create `auto_task` record, let services process it

### Importing Term Tree Data

1. Prepare CSV file with columns: `seq`, `tree_id`, `value`, `intro`, `level`, `parent_seq`, `is_category_node`
2. Run: `python scripts/import_term_tree_nodes.py data.csv -t TREE_ID -r ROOT_NODE_ID`
3. Use `--interactive` flag for confirmation before each insert
4. Script auto-creates missing concepts with translations

### Generating Academic Reviews

```python
from deepsearcher.configuration import init_rbase_config

config = init_rbase_config()  # Loads config.rbase.yaml by default

# For topic reviews
from deepsearcher.agent.overview_rag import OverviewRAG
overview_rag = OverviewRAG(
    llm=config.llm,
    reasoning_llm=config.reasoning_llm,
    writing_llm=config.writing_llm,
    translator=config.academic_translator,
    embedding_model=config.embedding_model,
    vector_db=config.vector_db,
    rbase_settings=config.rbase_settings
)
result = overview_rag.query("AI Applications in Healthcare")
```

## Important Notes

- **API Keys**: Stored in `.env` file or YAML configs (never commit to git)
- **Configuration Files**: `config.rbase.yaml` is the main config for RBase operations
- **Timezone**: Can be set in `rbase_settings.timezone` in config YAML
- **MNS Configuration**: Required for async classification services (see `services/README.md`)
- **Database Migrations**: See `database/mysql/README.md` for schema management
- **Vector DB Integrity**: Regularly run integrity checks on production data
- **Service Dependencies**: `task-dispatcher` should start before `classify-service`
