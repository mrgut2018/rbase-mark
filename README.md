# Deep Academic Research

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Deep Academic Research is an academic research assistance system based on RAG (Retrieval-Augmented Generation) technology, focusing on generating high-quality academic review articles. By combining vector databases and large language models, the system can perform in-depth analysis and summarization of specific research topics or researchers' academic achievements.

## 🚀 Core Features

### Academic Research Agents
- **OverviewRAG**: Research topic review generator that provides comprehensive analysis of specific research topics, generating complete reviews including background, theoretical foundations, methodologies, key findings, and emerging trends
- **PersonalRAG**: Researcher achievement review generator that performs in-depth analysis of specific researchers' academic achievements, generating personalized reviews including academic background, research evolution, core contributions, and academic impact
- **SummaryRAG**: Literature summary generator that provides intelligent summarization and synthesis of large volumes of literature
- **DiscussAgent**: Academic discussion agent that supports intelligent academic conversations with users, providing follow-up question functionality
- **ChainOfRAG**: Chain RAG agent that supports multi-step complex query processing
- **DeepSearch**: Deep search agent that provides more precise literature retrieval functionality
- **NaiveRAG**: Basic RAG agent that provides simple retrieval-augmented generation functionality

### Multi-Modal Support
- **Multiple LLM Support**: Supports various LLMs including OpenAI, Anthropic, DeepSeek, Gemini, TogetherAI, SiliconFlow, PPIO, Azure OpenAI, XAI, Ollama
- **Multiple Vector Database Support**: Supports Milvus and Oracle vector databases
- **Multiple Embedding Model Support**: Supports various embedding models including OpenAI, Voyage, Bedrock, SiliconFlow, Milvus
- **Multilingual Support**: Supports bilingual output in Chinese and English, with accurate translation of technical terms through the `AcademicTranslator` class

### API Services
- **RESTful API**: Provides complete HTTP API interfaces
- **Streaming Response**: Supports real-time streaming responses
- **Multiple Endpoints**: Includes discussion, summary, metadata query, question processing, and other functionalities

## 📖 Quick Start

### System Requirements

- Python >= 3.10
- Vector Database (Milvus or Oracle)
- MySQL Database (for storing academic literature metadata)

### Installation

```bash
# Clone repository
git clone https://github.com/toboto/deep-academic-research.git

# Create and activate virtual environment
cd deep-academic-research
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .
```

### Configuration

1. Copy configuration template:
```bash
cp config.yaml.example config.yaml
```

2. Modify configuration file with necessary parameters:
- LLM API keys
- Vector database connection information
- MySQL database connection information
- Other optional configurations

### Usage Examples

#### Generate Research Topic Review

```python
from deepsearcher.agent.overview_rag import OverviewRAG
from deepsearcher.configuration import Configuration

# Initialize configuration
config = Configuration()
config.load_config("config.yaml")

# Create OverviewRAG instance
overview_rag = OverviewRAG(
    llm=config.get_llm(),
    reasoning_llm=config.get_reasoning_llm(),
    writing_llm=config.get_writing_llm(),
    translator=config.get_translator(),
    embedding_model=config.get_embedding_model(),
    vector_db=config.get_vector_db(),
    rbase_settings=config.get_rbase_settings()
)

# Generate review
result = overview_rag.query("AI Applications in Healthcare")
```

#### Generate Researcher Achievement Review

```python
from deepsearcher.agent.persoanl_rag import PersonalRAG

# Create PersonalRAG instance
personal_rag = PersonalRAG(
    llm=config.get_llm(),
    reasoning_llm=config.get_reasoning_llm(),
    writing_llm=config.get_writing_llm(),
    translator=config.get_translator(),
    embedding_model=config.get_embedding_model(),
    vector_db=config.get_vector_db(),
    rbase_settings=config.get_rbase_settings()
)

# Generate review
result = personal_rag.query("Please write a research overview of Professor Zhang San")
```

#### Use Academic Discussion Agent

```python
from deepsearcher.agent.discuss_agent import DiscussAgent

# Create DiscussAgent instance
discuss_agent = DiscussAgent(
    llm=config.get_llm(),
    reasoning_llm=config.get_reasoning_llm(),
    translator=config.get_translator(),
    embedding_model=config.get_embedding_model(),
    vector_db=config.get_vector_db()
)

# Conduct academic discussion
result = discuss_agent.query(
    "What is deep learning?",
    user_action="question",
    background="User is learning basic AI knowledge",
    history=[],
    target_lang="en"
)
```

#### Start API Service

```bash
# Install dependencies
pip install -r requirements.txt

# Start API server (default config: config.rbase.yaml)
python scripts/start_api_server.py --verbose

# Specify host and port
python scripts/start_api_server.py --host 0.0.0.0 --port 8000 --verbose

# Specify config file
python scripts/start_api_server.py --config config.yaml --verbose

# Multi-worker mode (auto-calculates optimal worker count)
python scripts/start_api_server.py --workers 4 --verbose
```

After starting, you can access:
- API docs (Swagger UI): `http://localhost:PORT/docs`
- API docs (ReDoc): `http://localhost:PORT/redoc`
- Health check: `http://localhost:PORT/health`

## 🔧 System Architecture

### Core Components

1. **Academic Agent Module** (`deepsearcher/agent/`)
   - `OverviewRAG`: Research topic review generator
   - `PersonalRAG`: Researcher achievement review generator
   - `SummaryRAG`: Literature summary generator
   - `DiscussAgent`: Academic discussion agent
   - `ChainOfRAG`: Chain RAG agent
   - `DeepSearch`: Deep search agent
   - `NaiveRAG`: Basic RAG agent
   - `AcademicTranslator`: Academic translator

2. **Language Model Module** (`deepsearcher/llm/`)
   - Support for multiple LLM providers
   - Unified interface design
   - Streaming generation support

3. **Embedding Model Module** (`deepsearcher/embedding/`)
   - Support for multiple embedding models
   - Text vectorization processing
   - Semantic search support

4. **Vector Database Module** (`deepsearcher/vector_db/`)
   - Milvus vector database support
   - Oracle vector database support
   - Efficient semantic retrieval

5. **API Service Module** (`deepsearcher/api/`)
   - RESTful API interfaces
   - Streaming response support
   - Multiple endpoint functionalities

6. **Data Loading Module** (`deepsearcher/loader/`)
   - File loaders (PDF, text, JSON, etc.)
   - Web crawlers
   - Data splitters

### Data Flow

1. **Data Preprocessing**
   - Literature metadata extraction
   - Text chunking
   - Vectorization processing

2. **Knowledge Retrieval**
   - Semantic search
   - Relevance reordering
   - Result deduplication

3. **Content Generation**
   - Chapter content generation
   - Content optimization
   - Multilingual translation

## 📚 Examples and Demos

The project provides rich example code located in the `examples/` directory:

- `basic_example.py`: Basic usage example
- `overview_rag_demo.py`: Research topic review demo
- `personal_rag_demo.py`: Researcher achievement review demo
- `discuss_agent_demo.py`: Academic discussion agent demo
- `summary_rag_demo.py`: Literature summary demo
- `academic_translate_demo.py`: Academic translation demo
- `llm_demo.py`: Language model usage demo

## 🤝 Contributing

We welcome various forms of contributions, including but not limited to:

- Submitting issues and suggestions
- Improving documentation
- Submitting code improvements
- Sharing usage experiences

Please refer to [Contributing Guide](./CONTRIBUTING.md) for more details.

## 📄 License

This project is licensed under the Apache 2.0 License. See the [LICENSE](./LICENSE.txt) file for details.

## 🙏 Acknowledgments

This project is developed based on the [DeepSearcher](https://github.com/zilliztech/deep-searcher) project. We would like to express our gratitude to the original project's contributors.
