# Market Research Automation Tool

A modular pipeline that automates desk research for the paint & coatings industry. The system ingests a natural‑language brief, plans targeted search queries, collects and synthesises web content, and returns both an executive‑level report and structured data (news, Patents articles, conference events, Legalnews). It is exposed through a **FastAPI** micro‑service with **database-backed job persistence** and features an **automated RAG uploader** for post-research querying.

---

## 1 — Key Features

| Capability                               | Description                                                                                                                                                             |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Bucketed query planning**              | Gemini analyses the user brief and produces site‑restricted Google CSE queries, organised into *News*, *Patents*, *Conference*, *Legalnews* and *General* buckets.         |
| **Parallel custom‑search harvesting**    | Parameterised concurrency for Google CSE with per‑thread service instances to avoid throttling.                                                                         |
| **Context‑aware synthesis**              | Intermediate sub‑reports per 15‑URL batch; final executive report merges these into a cohesive analysis.                                                                |
| **Targeted structured extraction**       | Separate Gemini extractor returns normalised JSON objects (type, title, summary, date, source\_url) only from specific URLs allocated for structured data.                  |
| **Database-backed job persistence**      | A local **SQLite** database tracks the state of all submitted jobs (pending, running, completed, failed), ensuring state is not lost on server restart.                 |
| **Automated RAG collection creation**    | On job completion, automatically creates a dedicated RAG collection, converts all reports and data to PDF, and uploads them for querying.                                 |
| **Post-research RAG querying**           | API endpoints allow for conversational querying of a completed job's RAG collection, maintaining chat context for follow-up questions.                                   |
| **Configurable content freshness**       | Central `RECENT_YEARS` constant filters out search results, extractions, and analysis older than a defined period to ensure relevance.                                   |
| **Async & multithreaded orchestration**  | Asyncio + `ThreadPoolExecutor` for optimal IO‑bound and CPU‑bound step overlap.                                                                                         |
| **REST API**                             | `POST /api/research` (submit), `GET /api/research/...` (poll/retrieve), and `POST /api/rag/query` (ask).                                                                 |
| **Extensible design**                    | Each pipeline phase is its own module; easy to swap LLMs, add new data sources, or introduce caching.                                                                   |

---

## 2 — Directory Structure

```text
market_research_tool/
├─ api/                          # FastAPI service
│  ├─ models.py                  # Pydantic request / response models
│  └─ server.py                  # HTTP endpoints, job persistence, & RAG orchestration
├─ database/                     # SQLAlchemy models & session management
│  ├─ models.py                  # Defines the 'jobs' table schema
│  └─ session.py                 # DB engine and session configuration
├─ src/                          # Core pipeline implementation
│  ├─ config.py                  # Environment variable loading & validation
│  ├─ constants.py               # Centralised runtime limits
│  ├─ main.py                    # Orchestrator (execute_research_pipeline)
│  ├─ phase1_planner.py
│  ├─ phase2_searcher.py
│  ├─ phase3_intermediate_synthesizer.py
│  ├─ phase4_extractor.py
│  ├─ phase5_final_synthesizer.py
│  └─ rag_uploader.py            # Converts artifacts to PDF and uploads to RAG system
├─ reports/                      # Markdown reports (auto‑generated)
├─ extractions/                  # Structured JSON extractions (auto‑generated)
├─ jobs.db                       # SQLite database for job persistence
├─ requirements.txt
└─ .env.example                  # Template for secrets
```

---

## 3 — Installation

### 3.1 Prerequisites

*   Python 3.11+
*   A Google Cloud account with **Custom Search JSON API** enabled
*   Gemini API access (or adjust to another LLM)
*   Access to a RAG API service (for the upload and query features)

### 3.2 Set‑up

```bash
# clone
$ git clone <repo-url> market_research_tool && cd $_

# create isolated environment
$ python -m venv venv
$ source venv/bin/activate

# install dependencies
(venv) $ pip install -r requirements.txt

# copy secrets template
(venv) $ cp .env.example .env

# edit .env with your API keys, CSE ID, and RAG service details
```
> **Note:** The first time you run the API service, it will automatically create the `jobs.db` file.

---

## 4 — Running the Pipeline

### 4.1 CLI (one‑off batch)

```bash
(venv) $ python -m src.main <<EOF
Show me the latest innovations in Weatherability of Decorative Coatings.
What trends are emerging in the Sustainability of industrial coatings in 2025?
Find recent conferences or Patents discussing Scuff‑Resistance in coatings.
EOF
```

Progress is logged to STDOUT; final artefacts appear in `reports/` and `extractions/`.

### 4.2 API Service

```bash
(venv) $ uvicorn api.server:app --reload
```

Interactive OpenAPI documentation becomes available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

## 5 — API Reference

### 5.1 Submit a Job

`POST /api/research`

Submits a new research job. The `upload_to_rag` flag controls whether the results are sent to the RAG system upon completion.

```jsonc
{
  "query": "- Show me the latest innovations in Weatherability of Decorative Coatings.\n- What trends are emerging in the Sustainability of industrial coatings in 2025?\n- Find recent conferences or Patents discussing Scuff-Resistance in coatings.\n\nSearch tags/topics – Product, coating, architectural or similar.\nDatasources/URLs (https://www.paint.org/, https://www.coatingsworld.com/, https://www.pcimag.com/)",
  "upload_to_rag": true
}
```

Response `202 Accepted`

```json
{
  "job_id": "fbadce0d-f51a-4e1d-83ad-cd971c7ba4c7",
  "status": "pending",
  "status_url": "http://127.0.0.1:8000/api/research/status/fbadce0d-f51a-4e1d-83ad-cd971c7ba4c7",
  "result_url": "http://127.0.0.1:8000/api/research/result/fbadce0d-f51a-4e1d-83ad-cd971c7ba4c7"
}
```

### 5.2 Check Status

`GET /api/research/status/{job_id}` → `JobStatusResponse`

Polls the status of a job. The message will include RAG upload status if applicable.

```json
{
  "job_id": "...",
  "status": "completed",
  "message": "Job status is completed. RAG upload successful (Collection: orgid_research_job_...)"
}
```

### 5.3 Retrieve Result

`GET /api/research/result/{job_id}` → `ResearchResult`

Retrieves the final report and structured data. The `metadata` block contains RAG info if it was requested.

-   `final_report_markdown` — complete executive report
-   `extracted_data` — categorised list (`News` | `Patents` | `Conference` | `Legalnews` | `Other`)
-   `metadata` — timing, counts, and RAG info

```jsonc
// Snippet of the response structure
{
  "job_id": "...",
  "status": "completed",
  "original_query": "...",
  "final_report_markdown": "# Executive Summary\n...",
  "extracted_data": { "...": [] },
  "metadata": {
    "timestamp": "...",
    "extraction_summary": { "...": 0 },
    "rag_info": { // Included if upload_to_rag was true
      "upload_requested": true,
      "rag_status": "uploaded",
      "collection_name": "orgid_research_job_fbadce0d_...",
      "rag_error": null
    }
  }
}
```

### 5.4 Get RAG Collection Info

`GET /api/research/{job_id}/rag` → `RAGCollectionInfo`

Returns detailed information about the RAG collection associated with a specific job, including whether it's ready to be queried.

Response `200 OK`
```json
{
    "job_id": "fbadce0d-f51a-4e1d-83ad-cd971c7ba4c7",
    "rag_status": "uploaded",
    "collection_name": "orgid_research_job_fbadce0d_f51a_4e1d_83ad_cd971c7ba4c7",
    "rag_error": null,
    "can_query": true
}
```

### 5.5 Query the RAG Collection

`POST /api/rag/query` → `RAGQueryResponse`

Ask a question to a specific RAG collection. The system automatically manages chat history in the database for conversational follow-up.

```jsonc
// Request
{
    "collection_name": "orgid_research_job_fbadce0d_f51a_4e1d_83ad_cd971c7ba4c7",
    "question": "Which companies are leading in scuff-resistant coating technologies?"
}
```

Response `200 OK`
```json
{
    "collection_name": "orgid_research_job_fbadce0d_...",
    "question": "Which companies are leading in scuff-resistant coating technologies?",
    "answer": {
        "response": "Based on the provided documents, the key players in scuff-resistant coating technologies include...",
        "citations": [ /* ... */ ]
    }
}
```

---

## 6 — Configuration & Tuning

### 6.1 Pipeline Constants (`src/constants.py`)

This file centralises critical limits for the research pipeline:

| Constant                 | Purpose                                                                    | Default |
| ------------------------ | -------------------------------------------------------------------------- | ------- |
| `MAX_SEARCH_RESULTS`     | Google CSE results per query                                               | 4       |
| `MAX_SEARCH_WORKERS`     | Threads for CSE calls                                                      | 9       |
| `MAX_GENERAL_FOR_REPORT` | URLs allowed in the **General** bucket (feeds Phase‑3/5)                   | 18      |
| `MAX_PER_BUCKET_EXTRACT` | URLs per specialised bucket (feeds Phase‑4)                                | 9       |
| `EXTRACT_BATCH_SIZE`     | URLs processed per Gemini extract batch                                    | 18      |
| `MAX_GEMINI_PARALLEL`    | Concurrent Gemini extract calls                                            | 9       |
| `RECENT_YEARS`           | Filters out content older than N years to maintain freshness               | 2       |

### 6.2 Environment Variables (`.env`)
The `.env` file holds all necessary secrets. In addition to Google keys, the RAG uploader requires its own configuration:
-   `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_CSE_ID`: For core research.
-   `RAG_API_BASE_URL`, `RAG_API_TOKEN`, `RAG_API_ORG_ID`: For the RAG uploader and query system.

---

## 7 — Logging & Artefacts

*   **Job State:** Persisted in the `jobs.db` SQLite database file.
*   **Intermediate sub‑reports:** `reports/intermediate_reports/`
*   **Final reports:** `reports/`
*   **Structured JSON extractions:** `extractions/`
*   **STDOUT logs:** Encapsulate phase boundaries, counts, durations and error traces; suitable for piping into a log aggregator.

---

## 8 — Extending the Pipeline

1.  **Add a new data source**: update `phase1_planner.py` prompt to include the domain, adjust CSE queries as required.
2.  **Swap LLM**: provide an alternative client and swap calls in phases; ensure streaming token semantics are preserved.
3.  **Customize RAG Behavior**: Modify prompts, PDF generation, and API logic in `src/rag_uploader.py`.
4.  **Introduce caching**: layer a Redis cache around `_execute_single_query` and `extract_data_from_single_url` to reduce API spend.
5.  **Dockerisation**: create a slim Python image, copy project, install requirements, expose port 8000. Mount a volume for reports/extractions and `jobs.db` if persistence across containers is required.

---

## 9 — Testing & Quality

```bash
# run unit tests (pytest recommended)
(venv) $ pytest -q

# static typing
(venv) $ mypy src/ api/ database/

# style guide (PEP‑8 via ruff)
(venv) $ ruff check .
```

---

## 10 — Contribution Guidelines

*   Fork the repository & create a feature branch.
*   Follow the existing module structure; each phase should remain independently testable.
*   If adding database columns, consider migration strategies.
*   Run all tests and linters before submitting a PR.
*   Document any public‑facing changes (API, constants) in this README.

---

## 11 — License

Distributed under the **MIT License**. See `LICENSE` for details.

---

## 12 — Acknowledgements

*   Google GenAI SDK & Gemini models
*   Google Custom Search JSON API
*   FastAPI & Uvicorn
*   SQLAlchemy
*   ReportLab