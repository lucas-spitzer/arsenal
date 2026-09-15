# Arsenal: System Overview & Tech Stack

## Introduction

Arsenal is a private educational system with two surfaces:

- **Foundry** — a browser-based production studio that transforms trusted source content into structured lessons, visual artifacts, assessment questions, and related educational material.
- **Academy** — the learning surface for viewing and interacting with artifacts produced by Foundry (reading, studying, utilizing outputs, and related learner workflows).

Foundry’s production work is carried by three coordinated systems:

- **Intellex** — the intelligent knowledge base and source-processing system.
- **Mathesys** — the educational material generation system.
- **QnGen** — the question and assessment generation system.

Together, these systems let a user upload raw documents, media, and reference materials; convert those materials into a structured knowledge base; generate educational outputs; and produce questions that test the generated material. Academy is where those outputs are consumed.

The purpose of this document is to define Arsenal’s naming and organization, state the product vision at a high level, and summarize the technology stack (React/Vite frontend, FastAPI backend, RQ job queue, Python workers, Supabase storage/database, pgvector search, and OpenAI LLM layer).

## Naming & Organization

| Name | Role |
|------|------|
| **Arsenal** | Umbrella project and brand — shared SPA, API, and repository |
| **Foundry** | Production studio — produce and generate useful educational material |
| **Academy** | Learning surface — view, learn from, and utilize Foundry artifacts |
| **Intellex** | Foundry system — library / knowledge base and source processing |
| **Mathesys** | Foundry system — educational material generation |
| **QnGen** | Foundry system — question and assessment generation |

## System Vision

Arsenal should function as a private educational environment rather than a public SaaS application. It is intended primarily as a powerful personal tool: Foundry turns source material into polished learning assets; Academy is where those assets are used.

The ideal loop is:

1. Upload source documents, media, or notes into Foundry.
2. Intellex ingests and organizes those materials.
3. A production run is the Foundry work order: selected sources plus target artifacts (ebook, narration, study sheet, wiki knowledge, assessments). Wiki Knowledge treats the uploaded source file as the notes and writes canonical wiki entries.
4. Mathesys generates educational content from the structured source.
5. QnGen creates assessments from curated wiki knowledge.
6. Academy presents the resulting package for reading, study, and interaction. Canonical wiki entries appear in Academy Library. Open an entry to edit, deprecate, or rewrite it. There is no wiki tab on the rail.

Foundry is not merely a repository of files, a command-line tool, or a collection of scripts. It is a web-based production studio for AI-assisted educational content creation. Academy is the companion surface for putting that content to work.

## High-Level Architecture

```
React/Vite Frontend (Foundry + Academy)
        ↓
FastAPI Backend
        ↓
RQ Job Queue + Redis
        ↓
Python Workers
        ↓
Supabase Postgres + Supabase Storage + pgvector
        ↓
OpenAI LLM Layer
```

The frontend provides both Foundry and Academy interfaces. FastAPI handles API requests, validation, authentication checks, and job creation. RQ and Redis manage background job dispatch. Python workers execute long-running AI and document-processing workflows for Intellex, Mathesys, and QnGen. Supabase stores files, relational data, and vector embeddings. OpenAI provides the LLM and embedding layer.

## Mental Model

| Role | Component |
|------|-----------|
| Umbrella product | Arsenal |
| Private educational production studio | Foundry |
| Learning / consumption surface | Academy |
| Library | Intellex |
| Teacher/designer | Mathesys |
| Examiner | QnGen |
| Studio + Academy interface | React/Vite |
| Coordination layer | FastAPI |
| Work-order system | RQ/Redis |
| Automation factory | Python workers |
| Memory and storage | Supabase |
| Intelligence layer | AI Models |
