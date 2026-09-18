# Arsenal

Arsenal is a private educational system with two surfaces in one SPA:

- **Foundry** — browser-based **educational production studio**. Upload sources, run Intellex ingest and Wiki Knowledge, and generate Mathesys artifacts plus QnGen assessments over a queued worker pipeline.
- **Academy** — learning surface. **Library** is the catalog of artifacts, wiki entries, and assessments. Foundry produces; Academy curates.

| Foundry system | Role | Module |
|--------|------|--------|
| **Intellex** | Ingest and grounded knowledge: structured source (chapters/chunks/research) plus Wiki Knowledge → canonical `wiki_entries`. Not “Library.” | `intellex` |
| **Mathesys** | File artifacts from the structured source (ebook, narration, wiki JSON snapshot, study sheet). | `mathesys` |
| **QnGen** | Flashcards, quizzes, and scenarios from canonical wiki + evidence. | `qngen` |

Names, output kinds, and module ownership: [`docs/internal/system/system-overview.md`](docs/internal/system/system-overview.md). Mathesys file contracts: [`docs/internal/system/artifacts-catalog.md`](docs/internal/system/artifacts-catalog.md).

---

## High-Level Architecture

```mermaid
flowchart TD
    subgraph client["Browser — React / Vite SPA"]
        UI[Foundry + Academy UI]
        SBJS[supabase-js auth]
    end

    subgraph api["FastAPI Backend"]
        AUTH[Auth dependency<br/>require_approved_user]
        ROUTERS[Routers<br/>workspaces · sources · stages<br/>production-runs · wiki<br/>artifacts · assessments]
        SVC[Services<br/>source_upload · queue<br/>production_runs]
    end

    subgraph queue["Job Queue"]
        REDIS[(Redis)]
        RQ[RQ Queue]
    end

    subgraph worker["Python Worker"]
        RUNNER[PipelineRunner]
        EXEC[Stage Executors]
    end

    subgraph data["Supabase"]
        PG[(Postgres + pgvector)]
        STORE[(Storage bucket: sources)]
    end

    subgraph ext["External APIs"]
        OPENAI[OpenAI<br/>LLM + embeddings]
    end

    UI --> SBJS
    SBJS -- access token --> ROUTERS
    ROUTERS --> AUTH
    AUTH -- verify + approval --> PG
    ROUTERS --> SVC
    SVC -- store file --> STORE
    SVC -- rows --> PG
    SVC -- enqueue --> RQ
    RQ <--> REDIS
    RQ -- dispatch job --> RUNNER
    RUNNER --> EXEC
    EXEC --> OPENAI
    EXEC -- read/write --> PG
    EXEC -- read/write artifacts --> STORE
    UI -- poll status --> ROUTERS
```

The browser authenticates with Supabase directly (`supabase-js`) and sends the resulting access token to FastAPI on every request. FastAPI verifies the token and an approval check before serving data. Long-running AI work never blocks the request: the API enqueues a job on Redis/RQ, and a separate Python worker executes the pipeline, writing results back to Postgres and Storage that the UI polls.

---

## Request & Authentication Flow

```mermaid
sequenceDiagram
    participant U as User
    participant SPA as React SPA
    participant SB as Supabase Auth
    participant API as FastAPI
    participant DB as Postgres

    U->>SPA: Open /app
    SPA->>SB: Sign in (OAuth / magic link)
    SB-->>SPA: Session + access token
    SPA->>API: Request + Authorization: Bearer <token>
    API->>SB: Validate token (get user)
    API->>DB: Check account is approved
    alt Approved
        API-->>SPA: 200 + data
    else Not approved
        API-->>SPA: 403 Forbidden
    end
```

Every endpoint except `/health` requires `Authorization: Bearer <supabase-access-token>`. The `require_approved_user` dependency rejects invalid sessions (401) and unapproved accounts (403). The backend uses the Supabase **service role** key for data access; the service role key is never exposed to the frontend.

---

## Source Upload & Ingest

Uploading a source automatically queues an **ingest-only** production run (the Intellex base pipeline). PDFs are the only supported source type today.

```mermaid
sequenceDiagram
    participant SPA as React SPA
    participant API as FastAPI
    participant ST as Supabase Storage
    participant DB as Postgres
    participant RQ as Redis / RQ
    participant W as Worker

    SPA->>API: POST /workspaces/{id}/sources (multipart file)
    API->>API: validate_source_upload<br/>(PDF magic bytes, size, filename)
    API->>ST: Upload file to sources bucket
    API->>DB: INSERT source (status=stored)
    API->>DB: INSERT production_run (target_artifacts=[])
    API->>RQ: enqueue orchestrate_production_run
    API-->>SPA: 202 source + run queued
    RQ->>W: dispatch job
    W->>W: Run base Intellex pipeline
    W->>DB: Update source status → ready
```

---

## The Production Pipeline

A **production run** is one work order: selected sources plus `target_artifacts` (Intellex wiki, Mathesys files, QnGen assessments). Empty targets = ingest only. The backend builds an ordered pipeline (`build_pipeline`) and enqueues it. `PipelineRunner` executes each step and updates the run’s `pipeline` JSON so OPS can show progress.

### Pipeline composition

Intellex **base ingest** always runs (or is skipped when that source is already ingested). Optional steps are appended from `target_artifacts`. `wiki_knowledge` is Intellex, not Mathesys.

```mermaid
flowchart LR
    subgraph base["Intellex base ingest"]
        S1[store] --> S2[parse] --> S3[normalize-document] --> S4[trim-document-boundaries] --> S5[structure-document] --> S6[validate-structure] --> S7[chunk] --> S8[source-research] --> S9[web-enrichment]
    end

    subgraph optional["Optional — per target"]
        direction TB
        W1[wiki_knowledge]
        M1[create-ebook / generate-narration / generate-study-sheet / export-wiki-json]
        Q1[generate-flashcards / generate-questions / generate-scenarios]
    end

    S9 --> optional
```

| `target_artifact` | Pipeline step | Module | Output kind |
|-------------------|---------------|--------|-------------|
| `wiki_knowledge` | `transcribe-wiki-notes` + `structure-wiki-notes` | Intellex | Wiki entries |
| `electronic_book` | `create-ebook` | Mathesys | Artifact (EPUB) |
| `narration_audio` | `generate-narration` | Mathesys | Artifact |
| `study_sheet` | `generate-study-sheet` | Mathesys | Artifact (PDF) |
| `wiki_json` | `export-wiki-json` | Mathesys | Artifact (snapshot of wiki) |
| `flashcards` | `generate-flashcards` | QnGen | Assessments |
| `quizzes` | `generate-questions` | QnGen | Assessments |
| `scenarios` | `generate-scenarios` | QnGen | Assessments |

Canonical step lists: [`api/app/pipeline.py`](api/app/pipeline.py) and [`api/README.md`](api/README.md).

### Full pipeline execution

```mermaid
flowchart TD
    START([Production run queued]) --> RUNNING[status = running]

    subgraph intellex["Intellex ingest — always unless reused/skipped"]
        STORE[store]
        PARSE[parse]
        NORM[normalize-document]
        TRIM[trim-document-boundaries]
        STRUCT[structure-document]
        VAL[validate-structure]
        CHUNK[chunk]
        RESEARCH[source-research]
        WEB[web-enrichment]
        STORE --> PARSE --> NORM --> TRIM --> STRUCT --> VAL --> CHUNK --> RESEARCH --> WEB
    end

    subgraph wiki["Intellex wiki — if wiki_knowledge"]
        TWN[transcribe-wiki-notes]
        SWN[structure-wiki-notes]
        TWN --> SWN
    end

    subgraph mathesys["Mathesys — selected artifacts"]
        EBOOK[create-ebook]
        NAR[generate-narration]
        SHEET[generate-study-sheet]
        WJ[export-wiki-json]
    end

    subgraph qngen["QnGen — selected assessments"]
        FLASH[generate-flashcards]
        QUIZ[generate-questions]
        SCEN[generate-scenarios]
    end

    RUNNING --> STORE
    WEB --> wiki
    SWN --> WIKI[(wiki_entries)]
    WEB --> mathesys
    mathesys --> ART[(artifacts + Storage)]
    WIKI --> qngen
    qngen --> ASSESS[(flashcards · quizzes · scenarios)]
    qngen --> DONE([status = completed])

    DONE -.failure at any step.-> FAILED([status = failed<br/>error recorded])
```

Each stage step runs once per selected source and writes an immutable `stage_run`. Ingest builds the structured source (`document_chapters`, `ndr_segments`). Wiki Knowledge writes canonical `wiki_entries` from the source file as notes. Mathesys packages files; QnGen reads the wiki. A failed step marks the run `failed` and resets in-flight sources.

---

## Data Model

```mermaid
erDiagram
    workspaces ||--o{ sources : contains
    workspaces ||--o{ production_runs : has
    workspaces ||--o{ wiki_entries : has
    workspaces ||--o{ artifacts : has
    workspaces ||--o{ flashcards : has
    workspaces ||--o{ quizzes : has
    workspaces ||--o{ scenarios : has
    production_runs ||--o{ stage_runs : spawns
    production_runs }o--o{ sources : references
    sources ||--o{ ndr_segments : "chunked into"
    stages ||--o{ stage_runs : "executed as"

    workspaces {
        uuid id
        uuid owner_id
        text name
        text status
    }
    sources {
        uuid id
        text filename
        text storage_path
        text status
    }
    production_runs {
        uuid id
        uuid[] source_ids
        text[] target_artifacts
        jsonb pipeline
        text status
    }
    stage_runs {
        uuid id
        text stage_id
        text module
        jsonb output
        jsonb token_usage
    }
```

Stages are **versioned definitions** (`stage_id` + `version`, major.minor format such as `1.0` or `2.0`) seeded in Postgres; each execution creates a `stage_run` capturing the exact inputs, output, model, and token usage. Postgres has `pgvector` enabled for embedding-based search over NDR segments and wiki entries.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React + Vite + TypeScript, React Router |
| Auth | Supabase Auth (`supabase-js`) |
| Backend API | FastAPI (Python) |
| Job queue | RQ + Redis |
| Workers | Python (`PipelineRunner` + stage executors) |
| Database | Supabase Postgres + pgvector |
| File storage | Supabase Storage (`sources` bucket; per-source `parse/`, `structure/`, `narration/`, `artifacts/`) |
| LLM / embeddings | OpenAI |
| PDF parsing | LlamaParse (LlamaCloud, agentic tier) |

---

## Repository Layout

```text
Arsenal/
├── api/                      FastAPI backend + worker
│   └── app/
│       ├── routers/          HTTP endpoints
│       ├── services/         upload, queue, supabase, openai
│       ├── repositories/     Postgres data access
│       ├── intellex/         ingest, structure, research, wiki-knowledge stages
│       ├── mathesys/         ebook, narration, study sheet, wiki JSON export
│       ├── qngen/            flashcard / quiz / scenario stages
│       ├── worker/           PipelineRunner, stage executors, RQ jobs
│       └── pipeline.py       pipeline composition (base + optional steps)
├── app/                      React + Vite frontend
│   └── src/
│       ├── features/         auth + workspace providers
│       ├── components/foundry/   Foundry production UI
│       ├── components/academy/   Academy learning UI
│       └── lib/              API client + mappers
├── supabase/
│   └── setup/                greenfield SQL (01–04) + alter patches for existing DBs
├── docker/                   docker-compose (Redis)
└── docs/internal/            system overview & design notes
```

---

## Getting Started

Setup, environment variables, and the full endpoint reference live in [`api/README.md`](api/README.md). In short:

1. **Backend** — create a venv, install `api/requirements.txt`, populate `api/.env`, run `uvicorn app.main:app --reload --port 8000`.
2. **Queue + Worker** — start Redis (`docker compose up -d redis`), then run `python run_worker.py`.
3. **Database** — for a new Supabase project, run `01`–`04` in order (see [`supabase/setup/README.md`](supabase/setup/README.md)). Existing databases use the `alter-*.sql` patches in that same folder — see [`supabase/README.md`](supabase/README.md).
4. **Frontend** — point `VITE_API_BASE_URL` at the API and run the Vite dev server (see [`app/README.md`](app/README.md)).

Canonical organization (names, systems, output kinds): [`docs/internal/system/system-overview.md`](docs/internal/system/system-overview.md).
