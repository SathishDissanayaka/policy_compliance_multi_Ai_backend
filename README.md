# Policy Compliance Platform – Multi-AI Agent System

A full-stack policy-compliance assistant that lets HR and compliance teams ingest company and international policies, analyze employee-facing documents for violations, chat with a Gemini-backed assistant, and receive prioritized remediation guidance.

## Highlights
- **Document ingestion with OCR** – Extracts text from PDFs and images using PyPDF2 with TrOCR fallback, stores embeddings in Postgres/pgvector, and supports session-scoped temporary stores for uploaded evidence.
- **Policy-aware orchestration** – LangGraph routes each request through either the company-policy pipeline or a constrained general chat path based on intent classification.
- **Streaming analysis experience** – Flask streams LangGraph events over Server-Sent Events so the UI can display stage-by-stage progress and live token output.
- **Recommendation engine** – Gemini generates actionable remediation plans, enriched with authoritative policy snippets sourced from Supabase or the most recent analysis run.
- **Supabase-integrated RBAC** – JWT-protected endpoints enforce user roles, manage subscriptions, and allow admins to provision employee accounts.

## Architecture Overview
- **Frontend (`frontend/`)** – Vite + React client that authenticates with Supabase, uploads documents, renders chat/analysis streams, and visualizes recommendations.
- **Backend (`backend/`)** – Flask API with blueprints for documents, queries, recommendations, policies, chat sessions, and user management.
- **Orchestrator (`backend/orchestrator/`)** – LangGraph graphs plus an intent-aware `Orchestrator` class that manages session history, streaming execution, and routing.
- **Embedding & Storage** – Gemini embedding models feed pgvector tables (`documents`, `international_policy`, session-specific temp tables) and Supabase tables (`policy_contexts`, `subscriptions`, `chat_history_*`).
- **OCR Pipeline** – `utils/pdf_parser.py` distinguishes text-based vs. image-based PDFs and uses TrOCR+Poppler when native extraction fails.

## Prerequisites
- Python 3.13+
- Node.js 18+ (for the Vite frontend)
- PostgreSQL 15+ with the `pgvector` extension
- Supabase project (service-role key + JWT secret)
- Google Gemini API access (`GEMINI_API_KEY`)
- Poppler utilities (for PDF-to-image conversion during OCR)

## Backend Setup
1. `cd backend`
2. Create a virtual environment (optional but recommended):
   ```pwsh
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```pwsh
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. Configure the database (ensure pgvector is enabled) and run any migrations/scripts you maintain under `backend/db/migrations/` or via `run_migration.py`.
5. Populate policy data as needed (see **Data Seeding** below).
6. Start the API:
   ```pwsh
   flask run
   ```

### Key Environment Variables
Place these in `backend/.env`:

| Variable | Description |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key for table operations |
| `SUPABASE_JWT_SECRET` | JWT secret for verifying Supabase-issued tokens |
| `GEMINI_API_KEY` | Google Gemini API key for chat, embeddings, and recommendations |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection settings |
| `POPPLER_PATH` | (Windows) Absolute path to Poppler bin directory for OCR |
| `ENABLE_TROCR` | Toggle OCR fallback (`true` by default) |
| `TROCR_MODEL_NAME` | Optional override for the HuggingFace TrOCR model |

### Data Seeding & Storage
- Upload company policy PDFs via `/documents/upload` or populate the `documents` table manually (ensure `embedding vector(3072)` column exists).
- International regulations can be loaded through `/documents/upload/international` which tags rows in `international_policy` by filename.
- Session-scoped tables (`temp_documents_{session}` and `analyze_documents_{session}`) are created automatically per analysis run.
- The `policy_contexts` Supabase table caches curated context rows used by the recommendation pipeline.

## Frontend Setup
1. `cd frontend`
2. Install dependencies: `npm install`
3. Configure `.env` (e.g., `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, backend API base URL).
4. Run the dev server: `npm run dev`

## Core Workflows
1. **Interactive Chat** – `/queries/analyze/stream` streams LangGraph events (input validation → history → retrieval → Gemini response) so the frontend can render live progress.
2. **Document Analysis** – `/documents/analyze` downloads Supabase-hosted uploads, performs OCR, builds embeddings, retrieves relevant company/international policy chunks, and returns structured violations plus provenance.
3. **Recommendations** – `/recommendations/generate` enriches violations with contextual snippets and asks Gemini for prioritized remediation plans, returning confidences and summaries.
4. **User & Subscription Management** – `/user/*` routes leverage Supabase Auth admin APIs and the `subscriptions` table to support RBAC and billing flows.

## Running Tests
- Unit tests live in `backend/test_recommendation_agent.py`. Execute with:
  ```pwsh
  pytest backend
  ```

## Troubleshooting
- **LangGraph import errors** – Ensure `pip install -r requirements.txt` succeeded after installing Rust (PyO3) and setting `PYO3_CROSS_LIB_DIR` if you are on Python 3.13.
- **OCR blank output** – Confirm Poppler is installed and `ENABLE_TROCR=true`. Monitor console logs from `utils/pdf_parser.py` for fallback diagnostics.
- **Supabase permissions** – Service-role key is required for server-side insert/update. Client-side access should use anon key (frontend only).
- **Gemini quota/availability** – All LLM calls (chat, embeddings, recommendations) rely on `GEMINI_API_KEY`; check quotas if responses start failing.

## Folder Reference
```
backend/
  app.py               # Flask factory with blueprint registration
  agents/              # Document processing, retrieval, recommendation agents
  orchestrator/        # LangGraph graphs, streaming executor, event formatter
  routes/              # Flask blueprints (documents, queries, policies, chat, users)
  utils/               # OCR, embeddings, prompts, Supabase client
  db/                  # Connection helper, repositories, migrations
frontend/              # Vite + React UI (chat, policy analyzer, uploads)
docs/                  # Sample policy PDFs for seeding/testing
uploads/               # Locally staged documents when testing uploads
```

## Roadmap Ideas
- Automate database migrations (e.g., Alembic) for pgvector schema changes
- Expand recommendation heuristics with user feedback loops
- Add monitoring hooks for Gemini/Supabase usage and latency
- Package background OCR processing into a task queue for large document batches

---
Maintainers: see Supabase settings for configured JWT secrets and enable Poppler + Rust on new developer machines before installing requirements.
