# Vocal Analytics Service — System Design Document

## StreamLine Call Analytics Platform

**Author:** Gaurav Bansal (Technical Lead)
**Date:** 2026-03-28
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Recap & Scale Parameters](#2-problem-recap--scale-parameters)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Architecture Diagram](#4-architecture-diagram)
5. [Detailed Component Design](#5-detailed-component-design)
   - 5.1 Audio Ingestion Service
   - 5.2 Transcription Service
   - 5.3 AI Analysis Service
   - 5.4 SOP Compliance Engine
     - 5.4.1 SOP Creation & Management Module
   - 5.5 Data Store Layer
   - 5.6 Reporting & Export Service
   - 5.7 Notification & Alerting Service
   - 5.8 API Gateway & Auth
6. [Data Flow & Pipeline Architecture](#6-data-flow--pipeline-architecture)
7. [Database Schema Design](#7-database-schema-design)
   - 7.1 PostgreSQL Schema
   - 7.2 Elasticsearch Index Mapping
   - 7.3 Database Sizing & Capacity Planning
8. [Storage & Retention Policies](#8-storage--retention-policies)
9. [Technology Choices & Justification](#9-technology-choices--justification)
10. [Cost Analysis](#10-cost-analysis)
11. [Scale & Performance Analysis](#11-scale--performance-analysis)
12. [Security & Compliance](#12-security--compliance)
13. [Monitoring & Observability](#13-monitoring--observability)
14. [Failure Handling & Resilience](#14-failure-handling--resilience)
15. [Project Plan — 8 Week Delivery](#15-project-plan--8-week-delivery)
16. [Testing Strategy](#16-testing-strategy)
17. [Assumptions](#17-assumptions)
18. [Open Questions for Client](#18-open-questions-for-client)
19. [Risks & Mitigation](#19-risks--mitigation)
20. [Future Enhancements](#20-future-enhancements)

---

## 1. Executive Summary

StreamLine processes 15,000–20,000 customer support calls daily. Currently, only 2–3% are manually reviewed. This platform automates the extraction of structured insights from **every** call — issue categorization, resolution status, sentiment analysis, key themes, and SOP compliance — enabling operations teams to identify systemic issues in near real-time rather than days or weeks later.

The system is designed as an **event-driven, queue-based asynchronous pipeline** that transforms raw audio recordings into queryable, structured analytics with a target processing latency of **under 10 minutes per call** from recording completion to dashboard availability.

**Key architectural principles:**
- Event-driven async processing for scale and resilience
- Separation of concerns — each pipeline stage is independently scalable
- Cost optimization — self-hosted transcription, tiered LLM usage
- Graceful degradation — partial results over total failure
- Data retention policies aligned with regulatory requirements

---

## 2. Problem Recap & Scale Parameters

### Business Problem
- Supervisors manually review ~2–3% of calls — the remaining 97% are unanalyzed
- Emerging issues (billing errors, outages, product confusion) take days/weeks to surface
- No systematic SOP compliance checking across all calls
- No way to aggregate trends across call volume at scale

### Scale Numbers

| Metric | Value |
|--------|-------|
| Daily call volume | 15,000 – 20,000 |
| Average call duration | 5–7 minutes |
| Total daily audio | 75,000 – 140,000 minutes (~1,250 – 2,333 hours) |
| Audio file size (compressed) | ~1 MB/min (Opus/AAC) |
| Daily storage (audio) | ~75 – 140 GB |
| Monthly storage (audio) | ~2.25 – 4.2 TB |
| Peak hour factor | ~2.5x average (business hours concentration) |
| Peak calls/hour | ~4,000 – 5,000 |
| Peak calls/minute | ~65 – 85 |
| Average transcript size | ~3,000 – 5,000 tokens (~2–4 KB text) |
| Daily transcript volume | ~45M – 100M tokens |

### Processing Time Budget (per call)

| Stage | Target Latency |
|-------|---------------|
| Ingestion + validation | < 5 seconds |
| Transcription | 30 – 90 seconds |
| AI Analysis | 5 – 15 seconds |
| SOP Compliance Check | 5 – 15 seconds |
| Storage + indexing | < 3 seconds |
| **Total end-to-end** | **< 3 minutes typical, < 10 minutes worst case** |

---

## 3. High-Level Architecture

The system is composed of **two planes** — a **data processing pipeline** (automated, event-driven) and an **admin/management plane** (user-driven, synchronous API).

```
┌──────────────────────────────────────────────────────────────────────┐
│                     DATA PROCESSING PIPELINE                        │
│              (automated, sequential, queue-based)                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. Audio Ingestion Service     — Detect, validate, enqueue          │
│  2. Transcription Service       — Audio → timestamped transcript     │
│  3. AI Analysis Service         — Transcript → structured insights   │
│  4. SOP Compliance Engine       — Analysis → compliance report       │
│  5. Data Store Layer            — Persist to PG + ES + Redis + S3    │
│  6. Reporting & Export Service  — Query, aggregate, export (Excel)   │
│  7. Notification Service        — Alerts on violations & trends      │
│                                                                      │
│  Flow: 1 → 2 → 3 → 4 → 5 → (6, 7)                                  │
│  Note: 3 → 4 is sequential (compliance needs issue_category from 3)  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                     ADMIN / MANAGEMENT PLANE                        │
│            (user-driven, synchronous REST API)                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  A. Issue Category Management   — CRUD taxonomy, agent assignments   │
│  B. SOP Management Module       — Create, test, publish SOPs         │
│  C. API Gateway                 — Auth, RBAC, rate limiting          │
│                                                                      │
│  Reference data from A & B feeds into pipeline stages 3 & 4         │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Communication Pattern

- **Pipeline inter-service:** Async message queues (RabbitMQ / AWS SQS) — sequential stages
- **Admin plane:** Synchronous REST API (CRUD operations)
- **Reference data:** Pipeline workers load categories and SOPs from PostgreSQL (cached in memory, refreshed on change)
- **Client-facing:** REST API via API Gateway
- **Real-time updates:** WebSocket for dashboard live feed (optional Phase 2)

---

## 4. Architecture Diagram

### 4.1 End-to-End Data Flow

> **Key correction from earlier draft:** AI Analysis and SOP Compliance are **sequential**, not
> parallel. Compliance depends on the `issue_category` from Analysis to load the correct SOP.

```
 ══════════════════════════════════════════════════════════════════════════
 ║                      ADMIN / MANAGEMENT PLANE                        ║
 ║  (Operations & Quality Managers — via API or Excel import)           ║
 ║                                                                      ║
 ║  ┌──────────────────────┐    ┌──────────────────────────┐            ║
 ║  │ Issue Category Mgmt  │    │ SOP Management Module    │            ║
 ║  │                      │    │                          │            ║
 ║  │ • CRUD categories    │    │ • Create/edit SOPs       │            ║
 ║  │ • Hierarchical tree  │    │ • Excel import           │            ║
 ║  │ • Agent assignments  │    │ • Dry-run testing        │            ║
 ║  │                      │    │ • Publish / archive      │            ║
 ║  │ Feeds into:          │    │ • Version control        │            ║
 ║  │  → LLM prompt        │    │                          │            ║
 ║  │  → SOP matching      │    │ Feeds into:              │            ║
 ║  │  → Reporting filters │    │  → Compliance engine     │            ║
 ║  └──────────┬───────────┘    └────────────┬─────────────┘            ║
 ║             │                             │                          ║
 ║             └──────────┬──────────────────┘                          ║
 ║                        ▼                                             ║
 ║              ┌──────────────────┐                                    ║
 ║              │   PostgreSQL     │  (source of truth for              ║
 ║              │   Reference Data │   categories, SOPs, agents)        ║
 ║              └──────────────────┘                                    ║
 ══════════════════════════════════════════════════════════════════════════

 ══════════════════════════════════════════════════════════════════════════
 ║                      DATA PROCESSING PIPELINE                        ║
 ║  (Automated — triggered on every call recording)                     ║
 ║                                                                      ║
 ║            ┌─────────────────────┐                                   ║
 ║            │   Call Recording    │                                   ║
 ║            │   System (External) │                                   ║
 ║            └─────────┬───────────┘                                   ║
 ║                      │ Upload to S3 / Webhook                        ║
 ║                      ▼                                               ║
 ║      ┌───────────────────────────────┐                               ║
 ║      │   1. AUDIO INGESTION SERVICE  │                               ║
 ║      │                               │                               ║
 ║      │  • S3 event listener          │                               ║
 ║      │  • File validation (format,   │                               ║
 ║      │    duration, size, codec)     │                               ║
 ║      │  • Metadata extraction        │                               ║
 ║      │  • Dedup check                │                               ║
 ║      │  • Create call record in DB   │                               ║
 ║      └───────────────┬───────────────┘                               ║
 ║                      │                                               ║
 ║                      ▼                                               ║
 ║      ┌──────────────────────────────┐                                ║
 ║      │    TRANSCRIPTION QUEUE       │                                ║
 ║      │    (RabbitMQ / SQS)          │                                ║
 ║      └───────────────┬──────────────┘                                ║
 ║                      │                                               ║
 ║                      ▼                                               ║
 ║      ┌───────────────────────────────┐                               ║
 ║      │  2. TRANSCRIPTION SERVICE     │                               ║
 ║      │                               │                               ║
 ║      │  • Self-hosted Faster-Whisper │                               ║
 ║      │    (GPU workers, A10G)        │                               ║
 ║      │  • Speaker diarization        │                               ║
 ║      │    (pyannote: AGENT/CUSTOMER) │                               ║
 ║      │  • Timestamped segments       │                               ║
 ║      │  • Language detection         │                               ║
 ║      │  • Confidence scoring         │                               ║
 ║      │                               │                               ║
 ║      │  Output: diarized transcript  │                               ║
 ║      │  → stored in S3 (JSON)        │                               ║
 ║      └───────────────┬───────────────┘                               ║
 ║                      │                                               ║
 ║                      ▼                                               ║
 ║      ┌──────────────────────────────┐                                ║
 ║      │    ANALYSIS QUEUE            │                                ║
 ║      └───────────────┬──────────────┘                                ║
 ║                      │                                               ║
 ║                      ▼                                               ║
 ║      ┌───────────────────────────────┐    ┌──────────────────────┐   ║
 ║      │  3. AI ANALYSIS SERVICE       │◀───│ issue_categories     │   ║
 ║      │                               │    │ (loaded from DB,     │   ║
 ║      │  • Loads active categories    │    │  injected into LLM   │   ║
 ║      │    from DB → injects into     │    │  prompt as taxonomy) │   ║
 ║      │    LLM prompt as taxonomy     │    └──────────────────────┘   ║
 ║      │  • Tiered LLM routing:        │                               ║
 ║      │    GPT-4o-mini (90%)          │                               ║
 ║      │    GPT-4o (10% escalation)    │                               ║
 ║      │  • Extracts:                  │                               ║
 ║      │    - Issue category (FK)      │                               ║
 ║      │    - Resolution status        │                               ║
 ║      │    - Sentiment (per-segment)  │                               ║
 ║      │    - Key themes & pain points │                               ║
 ║      │    - Confidence scores        │                               ║
 ║      │  • Handles uncertainty:       │                               ║
 ║      │    low confidence → flag      │                               ║
 ║      │    incomplete → partial result│                               ║
 ║      │                               │                               ║
 ║      │  Output: structured analysis  │                               ║
 ║      │  with issue_category_id (FK)  │                               ║
 ║      └───────────────┬───────────────┘                               ║
 ║                      │                                               ║
 ║                      ▼  (sequential — needs issue_category           ║
 ║                         to match correct SOP)                        ║
 ║      ┌──────────────────────────────┐                                ║
 ║      │    COMPLIANCE QUEUE          │                                ║
 ║      └───────────────┬──────────────┘                                ║
 ║                      │                                               ║
 ║                      ▼                                               ║
 ║      ┌───────────────────────────────┐    ┌──────────────────────┐   ║
 ║      │  4. SOP COMPLIANCE ENGINE     │◀───│ sop_definitions      │   ║
 ║      │                               │    │ + sop_category_map   │   ║
 ║      │  • Match SOP by category_id   │    │ (loaded from DB,     │   ║
 ║      │    via sop_category_mappings  │    │  matched by issue    │   ║
 ║      │  • HYBRID evaluation:         │    │  category FK)        │   ║
 ║      │                               │    └──────────────────────┘   ║
 ║      │    Rule Engine (deterministic)│                               ║
 ║      │    ├ Keyword match            │                               ║
 ║      │    ├ Timing check             │                               ║
 ║      │    └ Sequence check           │                               ║
 ║      │                               │                               ║
 ║      │    LLM Judge (nuance)         │                               ║
 ║      │    ├ Empathy assessment       │                               ║
 ║      │    ├ Escalation judgment      │                               ║
 ║      │    └ Resolution quality       │                               ║
 ║      │                               │                               ║
 ║      │  • Deviation flagging         │                               ║
 ║      │  • Severity scoring           │                               ║
 ║      │                               │                               ║
 ║      │  Output: compliance report    │                               ║
 ║      │  with per-step pass/fail      │                               ║
 ║      └───────────────┬───────────────┘                               ║
 ║                      │                                               ║
 ║                      ▼                                               ║
 ║      ┌──────────────────────────────┐                                ║
 ║      │    STORAGE QUEUE             │                                ║
 ║      └───────────────┬──────────────┘                                ║
 ║                      │                                               ║
 ║                      ▼                                               ║
 ║      ┌───────────────────────────────────────────────────────────┐   ║
 ║      │              5. DATA STORE LAYER                          │   ║
 ║      │                                                           │   ║
 ║      │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │   ║
 ║      │  │ PostgreSQL   │  │Elasticsearch │  │    Redis      │    │   ║
 ║      │  │ (RDS)        │  │(OpenSearch)  │  │ (ElastiCache) │    │   ║
 ║      │  │              │  │              │  │               │    │   ║
 ║      │  │ • calls      │  │ • full-text  │  │ • real-time   │    │   ║
 ║      │  │ • transcripts│  │   transcript │  │   counters    │    │   ║
 ║      │  │ • analysis   │  │   search     │  │ • cached      │    │   ║
 ║      │  │   results    │  │ • dashboard  │  │   aggregations│    │   ║
 ║      │  │ • compliance │  │   aggregates │  │ • rate limits │    │   ║
 ║      │  │ • categories │  │ • faceted    │  │               │    │   ║
 ║      │  │ • SOPs       │  │   filtering  │  │ TTL: 5m-24h  │    │   ║
 ║      │  │ • agents     │  │              │  │               │    │   ║
 ║      │  │ • mat. views │  │ Rollover:    │  └──────────────┘    │   ║
 ║      │  │              │  │  monthly idx │                      │   ║
 ║      │  └──────────────┘  └──────────────┘  ┌──────────────┐    │   ║
 ║      │                                      │     S3        │    │   ║
 ║      │  Source of truth   Query accelerator  │              │    │   ║
 ║      │  for all data      for dashboards     │ • audio files│    │   ║
 ║      │                                      │ • transcripts│    │   ║
 ║      │                                      │ • exports    │    │   ║
 ║      │                                      │              │    │   ║
 ║      │                                      │ Lifecycle:   │    │   ║
 ║      │                                      │ Std→IA→Glacr │    │   ║
 ║      │                                      └──────────────┘    │   ║
 ║      └──────────────────────────┬────────────────────────────────┘   ║
 ║                                 │                                    ║
 ║                ┌────────────────┼────────────────┐                   ║
 ║                │                                 │                   ║
 ║                ▼                                 ▼                   ║
 ║  ┌──────────────────────┐          ┌──────────────────────────┐      ║
 ║  │ 6. REPORTING &       │          │ 7. NOTIFICATION SERVICE  │      ║
 ║  │    EXPORT SERVICE    │          │                          │      ║
 ║  │                      │          │ • Compliance violation   │      ║
 ║  │ • REST API           │          │   alerts (immediate)     │      ║
 ║  │ • Aggregation queries│          │ • Issue spike detection  │      ║
 ║  │   (PG + ES + Redis)  │          │ • Sentiment drop alerts  │      ║
 ║  │ • Excel export       │          │ • Agent perf warnings    │      ║
 ║  │ • PDF reports        │          │                          │      ║
 ║  │ • Dashboard data     │          │ Channels:                │      ║
 ║  │                      │          │  Slack / Email / Webhook │      ║
 ║  └──────────┬───────────┘          └──────────────────────────┘      ║
 ║             │                                                        ║
 ══════════════════════════════════════════════════════════════════════════

               │
               ▼
 ┌──────────────────────────┐
 │  8. API GATEWAY          │
 │                          │
 │  • JWT authentication    │
 │  • RBAC (admin,          │
 │    supervisor, analyst,  │
 │    viewer)               │
 │  • Rate limiting         │
 │  • Request routing       │
 │  • API versioning (v1)   │
 └──────────┬───────────────┘
            │
    ┌───────┴────────┐
    │                │
    ▼                ▼
 ┌─────────┐  ┌──────────────────┐
 │ Ops &   │  │ Quality Managers │
 │ Quality │  │ (Admin Plane)    │
 │ Teams   │  │                  │
 │         │  │ • Manage SOPs    │
 │ • View  │  │ • Manage issue   │
 │  reports│  │   categories     │
 │ • Excel │  │ • Agent assign.  │
 │  export │  │ • Dry-run tests  │
 │ • Alerts│  │                  │
 └─────────┘  └──────────────────┘
```

### 4.2 Queue-Based Pipeline Architecture

```
                                    SEQUENTIAL PIPELINE
                                    (each stage depends on previous output)

┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐
│  Audio   │───▶│ Transcribe   │───▶│   Analyze    │───▶│  Compliance  │───▶│  Store    │
│  Ingest  │    │   Queue      │    │   Queue      │    │   Queue      │    │  Queue    │
└──────────┘    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └─────┬─────┘
                       │                   │                   │                  │
                       ▼                   ▼                   ▼                  ▼
                ┌────────────┐      ┌────────────┐      ┌────────────┐     ┌──────────┐
                │  Workers   │      │  Workers   │      │  Workers   │     │ Workers  │
                │  (GPU)     │      │  (CPU)     │      │  (CPU)     │     │ (CPU)    │
                │  N=3-5     │      │  N=5-10    │      │  N=3-5     │     │ N=2-3    │
                │            │      │            │      │            │     │          │
                │ Faster-    │      │ LLM API    │      │ Rule eng.  │     │ PG write │
                │ Whisper    │      │ calls      │      │ + LLM API  │     │ ES index │
                │ + pyannote │      │ (GPT-4o-   │      │            │     │ Redis    │
                │            │      │  mini/4o)  │      │ Loads SOPs │     │ counters │
                │ Output:    │      │            │      │ by issue   │     │ S3 store │
                │ diarized   │      │ Loads:     │      │ category   │     │          │
                │ transcript │      │ categories │      │ from DB    │     │          │
                └────────────┘      │ from DB    │      └────────────┘     └──────────┘
                                    └────────────┘

                       ▲                                      ▲
                       │          REFERENCE DATA              │
                       │    ┌───────────────────────┐         │
                       │    │  PostgreSQL            │         │
                       └────│  • issue_categories   │─────────┘
                            │  • sop_definitions    │
                            │  • sop_category_map   │
                            │  • agents             │
                            └───────────────────────┘

                                    FAILURE HANDLING

               Dead Letter ◀──────── Failed messages at any stage ──────▶ DLQ
               Queue (DLQ)     (retry 3x with backoff, then DLQ)

               DLQ messages → visible in admin dashboard → one-click reprocess
```

### 4.3 Deployment Topology

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        AWS / Cloud Provider                              │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │  ECS / EKS       │  │  GPU Nodes   │  │   Managed Services       │   │
│  │  (Fargate)       │  │  (g5.xlarge) │  │                          │   │
│  │                  │  │              │  │ • RDS PostgreSQL         │   │
│  │ Pipeline:        │  │ • Faster-    │  │   (Multi-AZ, r6g.large) │   │
│  │ • Ingestion      │  │   Whisper    │  │   + read replica        │   │
│  │ • Analysis       │  │   workers   │  │ • ElastiCache Redis      │   │
│  │ • Compliance     │  │ • pyannote  │  │   (t3.medium)            │   │
│  │                  │  │              │  │ • OpenSearch             │   │
│  │ API:             │  │ Auto-scale   │  │   (t3.medium × 2)       │   │
│  │ • Reporting      │  │ 2-6 nodes    │  │ • S3 (audio + exports)  │   │
│  │ • SOP Admin      │  │ Spot + OD    │  │ • SQS queues (6 + DLQs) │   │
│  │ • Category Admin │  │ fallback     │  │ • CloudWatch + Grafana  │   │
│  │ • API Gateway    │  │              │  │ • SES (email alerts)     │   │
│  │ • Notification   │  │              │  │                          │   │
│  └──────────────────┘  └──────────────┘  └──────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                    VPC / Private Network                         │    │
│  │   All inter-service communication within private subnets        │    │
│  │   GPU nodes in private subnet with NAT for LLM API calls       │    │
│  │   API Gateway is only public-facing endpoint                    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Detailed Component Design

### 5.1 Audio Ingestion Service

**Purpose:** Entry point. Detects new call recordings, validates them, creates a tracking record, and enqueues for transcription.

**Trigger mechanism:**
- **Primary:** S3 event notifications (ObjectCreated) → triggers Lambda / service webhook
- **Fallback:** Periodic polling (every 60s) for missed events
- **Alternative:** REST API endpoint for direct upload (for testing / manual ingestion)

**Validation checks:**
| Check | Action on Failure |
|-------|------------------|
| File format (WAV, MP3, OGG, FLAC, M4A) | Reject, log error |
| File size (> 10KB, < 500MB) | Reject, log error |
| Audio duration (> 10 seconds, < 120 minutes) | Reject with reason |
| Codec integrity (can be decoded) | Reject, move to quarantine |
| Duplicate check (hash-based) | Skip, log as duplicate |
| Required metadata present (agent_id, call_id, timestamp) | Reject or enqueue with missing metadata flag |

**Metadata extraction:**
- Call ID, agent ID, customer ID (from filename convention or companion metadata file)
- Call start/end timestamps
- Duration
- File format and codec
- Source system identifier

**Output:** Creates a `call` record in PostgreSQL with status `QUEUED`, publishes message to `transcription-queue`.

**Scaling:** Stateless — horizontally scalable. 2 instances sufficient for 20K/day.

---

### 5.2 Transcription Service

**Purpose:** Converts audio recordings to timestamped, speaker-diarized text transcripts.

**Technology choice: Self-hosted Faster-Whisper (large-v3)**

**STT Provider Comparison (at ~3M minutes/month):**

| Provider | Cost/min | Monthly Cost | Diarization | Data Privacy | Ops Burden |
|----------|----------|-------------|-------------|-------------|-----------|
| **Self-hosted Faster-Whisper (A10G spot)** | ~$0.0004 | **$1,200–1,600** | Needs pyannote | In-VPC | High |
| **Self-hosted Faster-Whisper (A10G on-demand)** | ~$0.0012 | **$3,600** | Needs pyannote | In-VPC | High |
| OpenAI Whisper API | $0.006 | ~$18,000 | No | Leaves infra | None |
| Deepgram Nova-2 | $0.0036–0.0043 | ~$10,800–12,900 | Built-in | Leaves infra | None |
| Azure Batch | $0.01 | ~$30,000 | Built-in | Azure cloud | Low |
| Google Cloud STT | $0.012–0.016 | ~$36,000–48,000 | Built-in | GCP cloud | Low |
| AWS Transcribe | $0.015–0.024 | ~$47,250 | Built-in | AWS cloud | Low |

**Why self-hosted over API:**
| Factor | Cloud API (Whisper/Deepgram) | Self-hosted Faster-Whisper |
|--------|------------------------------|---------------------------|
| Cost at 3M min/month | $10,800–$47,250/mo | **$1,200–3,600/mo** |
| Latency | Network round-trip + queue | Local, predictable |
| Data privacy | Audio leaves your infra | **Audio stays in your VPC** |
| Speaker diarization | Varies (Deepgram: yes, Whisper: no) | pyannote integration |
| Rate limits | Yes | No |
| Scaling control | Limited | Full control |
| Ops overhead | None | Requires GPU instance management |

> **Note for budget-constrained clients:** If GPU operations expertise is limited, Deepgram Nova-2 at ~$10K–13K/month is the best managed alternative — competitive accuracy with Whisper, built-in diarization, and zero infrastructure overhead.

**Why Faster-Whisper over standard Whisper:**
- 4x faster inference with CTranslate2 backend
- 2x less memory usage
- Same accuracy (uses same model weights)
- Real-time factor: ~0.05–0.1x on A10G (a 6-min call processes in 18–36 seconds)

**GPU throughput estimates (Faster-Whisper large-v3):**

| GPU | Instance | RTF | Min audio/hr | Calls/hr (6 min avg) | On-demand $/hr | Spot $/hr | Monthly (on-demand) |
|-----|----------|-----|-------------|---------------------|---------------|-----------|-------------------|
| NVIDIA T4 | g4dn.xlarge | ~0.15x | 400 | ~65 | $0.526 | $0.16–0.20 | ~$380 |
| NVIDIA A10G | g5.xlarge | ~0.06x | 1,000 | ~165 | $1.006 | $0.30–0.45 | ~$730 |
| NVIDIA A100 40GB | p4d (shared) | ~0.03x | 2,000 | ~330 | ~$4.10 | ~$1.50 | ~$2,950 |

*RTF = Real-Time Factor. RTF 0.06 means a 6-min call processes in ~22 seconds.*

**Recommended setup:**
- **3x g5.xlarge (A10G)** base instances = ~500 calls/hour sustained throughput
- Auto-scale to **5 instances** during peak business hours (9am–6pm)
- Use **spot instances** for 60–70% cost savings (with on-demand fallback)
- Daily processing need: 120K min / ~1,000 min per GPU-hour = ~120 GPU-hours
- **Estimated cost: $1,200–1,600/mo (spot) or $2,200–3,650/mo (on-demand)**

**Speaker diarization:**
- Integrate **pyannote-audio** for speaker diarization
- Labels: AGENT, CUSTOMER (2-speaker model for call center use case)
- Applied as post-processing step after Whisper transcription
- Adds ~5–10 seconds per call

**Output format:**
```json
{
  "call_id": "CALL-20260328-00142",
  "language": "en",
  "duration_seconds": 385,
  "transcription_confidence": 0.94,
  "segments": [
    {
      "start": 0.0,
      "end": 4.2,
      "speaker": "AGENT",
      "text": "Thank you for calling StreamLine, my name is Sarah. How can I help you today?",
      "confidence": 0.97
    },
    {
      "start": 4.5,
      "end": 12.8,
      "speaker": "CUSTOMER",
      "text": "Hi, I've been charged twice for my subscription this month and I'd like a refund.",
      "confidence": 0.92
    }
  ]
}
```

**Error handling:**
- Audio too noisy (confidence < 0.5): flag for manual review, still proceed with best-effort transcript
- Unsupported language: detect and flag, attempt English transcription as fallback
- GPU OOM: re-queue with smaller batch size
- Retry policy: 3 attempts with exponential backoff, then DLQ

---

### 5.3 AI Analysis Service

**Purpose:** Extract structured insights from the transcript using an LLM.

**Technology choice: Tiered LLM approach**

| Tier | Model | Use Case | Cost/1M tokens (in/out) | Est. Monthly (20K calls/day) |
|------|-------|----------|------------------------|---------------------------|
| Primary (bulk) | GPT-4o-mini | Standard calls, high confidence | $0.15 / $0.60 | ~$600 |
| Escalation | GPT-4o | Low-confidence results, complex calls | $2.50 / $10.00 | ~$150 (10% of calls) |
| Alternative primary | Claude Haiku 3.5 | Cost-effective alternative with batch API | $0.80 / $4.00 | ~$950 (or ~$475 batch) |
| Alternative escalation | Claude Sonnet 4 | Higher accuracy alternative to GPT-4o | $3.00 / $15.00 | ~$210 (10% of calls) |

*Token estimates per call: ~4,500 input tokens (1,500 system prompt + 3,000 transcript) + ~500 output tokens.*
*Batch API (OpenAI/Anthropic): 50% discount for non-real-time processing — our pipeline qualifies.*

**Why tiered:**
- 85–90% of calls are routine — GPT-4o-mini handles them accurately at 15x lower cost
- Complex/ambiguous calls get escalated to GPT-4o for higher accuracy
- Keeps monthly LLM cost at ~$800–1,500 instead of ~$10,000+

**Escalation criteria (auto-promote to GPT-4o):**
- GPT-4o-mini confidence score < 0.7 on any field
- Transcript contains escalation keywords ("supervisor", "cancel", "legal", "complaint")
- Call duration > 20 minutes (complex interaction)
- Multi-issue calls (> 2 detected issues)

**Structured output schema:**
```json
{
  "call_id": "CALL-20260328-00142",
  "analysis_version": "1.0",
  "model_used": "gpt-4o-mini",
  "processing_time_ms": 3200,

  "issue": {
    "primary_category": "billing",
    "sub_category": "duplicate_charge",
    "description": "Customer was charged twice for monthly subscription",
    "confidence": 0.95
  },

  "resolution": {
    "status": "resolved",
    "action_taken": "refund_initiated",
    "description": "Agent initiated refund for duplicate charge, confirmed 5-7 business day timeline",
    "confidence": 0.92
  },

  "sentiment": {
    "overall": "negative_to_neutral",
    "customer_start": "frustrated",
    "customer_end": "satisfied",
    "trajectory": "improving",
    "score": -0.3,
    "segments": [
      {"range": "0:00-2:00", "sentiment": "frustrated", "score": -0.7},
      {"range": "2:00-4:30", "sentiment": "neutral", "score": -0.1},
      {"range": "4:30-6:25", "sentiment": "satisfied", "score": 0.5}
    ]
  },

  "themes": ["duplicate_billing", "refund_request", "subscription_management"],

  "pain_points": [
    "Customer had to call to discover the duplicate charge — no proactive notification",
    "Refund timeline of 5-7 days perceived as too long"
  ],

  "escalation": {
    "detected": false,
    "type": null
  },

  "call_metadata": {
    "is_repeat_caller": null,
    "issue_complexity": "low",
    "agent_tone": "professional_empathetic"
  },

  "flags": {
    "requires_manual_review": false,
    "incomplete_input": false,
    "low_confidence_fields": []
  }
}
```

**Prompt engineering approach:**
- System prompt defines the role, output schema, and category taxonomy
- Categories are loaded dynamically from a configuration store (not hardcoded)
- Few-shot examples embedded in the prompt for consistent formatting
- JSON mode / structured outputs enforced via API parameter (OpenAI function calling or response_format)
- Temperature: 0.1 (low variance for consistency)

**Handling uncertainty and incomplete input:**
- Each field has an explicit `confidence` score (0.0–1.0)
- If transcript is partial (< 30 seconds or < 50 words): mark `incomplete_input: true`, still extract what's possible
- If AI is uncertain on a field: set confidence < 0.7, add field name to `low_confidence_fields`
- If the call is garbled/unintelligible: return `requires_manual_review: true` with whatever partial data was extracted
- **Never fabricate** — if uncertain, the schema explicitly supports "unknown" values

**Scaling:**
- Stateless workers, horizontally scalable
- 5–10 concurrent workers sufficient (LLM calls are I/O bound, not CPU bound)
- Rate limiting / backoff for LLM API rate limits

---

### 5.4 SOP Compliance Engine

**Purpose:** Check each call against the applicable Standard Operating Procedure and flag deviations.

**This is the building block that interests me most** — it bridges rule-based determinism with LLM flexibility, and getting it wrong has direct operational consequences (false positives erode trust, false negatives miss real violations).

**SOP Definition Model:**

SOPs are defined as versioned YAML documents stored in PostgreSQL, with a structure that separates **rule-based checks** (deterministic) from **judgment-based checks** (LLM-evaluated):

```yaml
sop_id: "SOP-BILLING-001"
version: "2.1"
call_types: ["billing", "refund", "payment_issue"]
effective_from: "2026-01-15"

steps:
  - id: "greeting"
    type: "rule"
    description: "Agent must greet with company name and their own name"
    check: "transcript_contains"
    parameters:
      speaker: "AGENT"
      segment: "first_60_seconds"
      must_contain_any: ["StreamLine", "Streamline"]
      must_contain_any_2: ["my name is", "this is", "I'm"]
    severity: "minor"

  - id: "identity_verification"
    type: "rule"
    description: "Agent must verify customer identity before account access"
    check: "transcript_contains"
    parameters:
      speaker: "AGENT"
      segment: "first_180_seconds"
      must_contain_any: ["verify", "confirm", "account number", "date of birth", "last four digits"]
    severity: "major"

  - id: "empathy_acknowledgment"
    type: "llm_judgment"
    description: "Agent must acknowledge customer's issue with empathy before jumping to resolution"
    evaluation_prompt: |
      Did the agent acknowledge the customer's frustration or issue
      with empathy before moving to troubleshooting or resolution steps?
      Look for phrases showing understanding, not just procedural responses.
    severity: "minor"

  - id: "resolution_confirmation"
    type: "llm_judgment"
    description: "Agent must confirm the resolution with the customer and ask if there's anything else"
    evaluation_prompt: |
      Did the agent clearly confirm what actions were taken to resolve the issue,
      verify the customer understood, and ask if there was anything else they needed help with?
    severity: "major"

  - id: "closing_script"
    type: "rule"
    description: "Agent must use proper closing"
    check: "transcript_contains"
    parameters:
      speaker: "AGENT"
      segment: "last_60_seconds"
      must_contain_any: ["thank you for calling", "anything else I can help", "have a great day"]
    severity: "minor"
```

**Hybrid evaluation approach:**

```
           Transcript + Analysis Result
           (includes issue_category_id)
                        │
                        ▼
              ┌─────────────────────────┐
              │ Load applicable SOPs    │
              │ via sop_category_map    │
              │ JOIN on category_id     │
              └────────────┬────────────┘
                           │
                ┌──────────┼──────────┐
                │                     │
                ▼                     ▼
       ┌─────────────────┐  ┌─────────────────────┐
       │  Rule Engine     │  │  LLM Judge           │
       │  (deterministic) │  │  (judgment calls)    │
       │                  │  │                      │
       │  • Keyword match │  │  • Send transcript + │
       │  • Segment check │  │    evaluation prompt │
       │  • Timing check  │  │  • Get pass/fail +   │
       │  • Sequence check│  │    reasoning         │
       │                  │  │  • Confidence score   │
       └────────┬─────────┘  └──────────┬───────────┘
                │                       │
                └───────────┬───────────┘
                            ▼
                  ┌─────────────────────┐
                  │  Compliance Report  │
                  │  (per call per SOP) │
                  └─────────────────────┘
```

**Why hybrid over pure-LLM:**
- Rule-based checks are **deterministic, fast, and free** — no reason to use LLM tokens for keyword matching
- LLM-based checks handle **nuance** that rules can't (empathy, judgment quality, contextual appropriateness)
- Hybrid gives **explainable results** — rule violations have clear evidence, LLM judgments include reasoning
- Reduces LLM cost by ~40–60% vs sending everything to LLM

**Compliance output format:**
```json
{
  "call_id": "CALL-20260328-00142",
  "sop_id": "SOP-BILLING-001",
  "sop_version": "2.1",
  "overall_compliance_score": 0.85,
  "status": "partial_compliance",

  "checks": [
    {
      "step_id": "greeting",
      "type": "rule",
      "passed": true,
      "evidence": "Agent said 'Thank you for calling StreamLine, my name is Sarah' at 0:00-0:04",
      "severity": "minor"
    },
    {
      "step_id": "empathy_acknowledgment",
      "type": "llm_judgment",
      "passed": false,
      "reasoning": "Agent immediately asked for account number without acknowledging the customer's frustration about being charged twice. No empathy phrases detected before jumping to resolution steps.",
      "confidence": 0.88,
      "severity": "minor"
    }
  ],

  "violations": [
    {
      "step_id": "empathy_acknowledgment",
      "severity": "minor",
      "description": "Agent did not acknowledge customer frustration before proceeding"
    }
  ],

  "violation_count": {"critical": 0, "major": 0, "minor": 1},
  "requires_supervisor_review": false
}
```

**SOP management:**
- SOPs are versioned — when updated, old calls retain their compliance score against the SOP version at the time
- Admin API for CRUD operations on SOPs
- Call type → SOP mapping is many-to-many via `sop_category_mappings` (a call might match multiple SOPs)
- SOP matching uses `analysis_results.issue_category_id` → looks up matching SOPs via `sop_category_mappings` JOIN

#### 5.4.1 SOP Creation & Management Module

**The problem:** SOPs are defined by **quality managers and operations leads** — non-technical business users. Expecting them to write YAML is unrealistic. We need a management layer that lets business users author SOPs through a structured interface, while YAML remains the internal storage format.

**Approach: Form-based Admin API + optional future UI**

Since building a full web UI is out of scope for the 8-week delivery (no frontend team), we deliver:
1. A **well-structured Admin REST API** for SOP CRUD operations
2. A **spreadsheet-based import** option (Excel/CSV) for bulk SOP creation
3. **YAML as internal format** — the API accepts structured JSON, converts to YAML internally
4. A **Postman collection / API documentation** so the client's team (or a future UI) can interact with it

**SOP creation flow:**

```
Business User                    System
─────────────                    ──────

Option A: API (JSON body)
  POST /api/v1/sops
  {                              ┌─────────────────────┐
    "name": "Billing SOP",       │ Validate structure   │
    "call_types": ["billing"],   │ Convert to YAML      │
    "steps": [                   │ Store in PostgreSQL   │
      {                          │ Version management    │
        "description": "...",    │ Mark as DRAFT         │
        "type": "rule",          └──────────┬────────────┘
        "check_type": "keyword",            │
        "keywords": [...],                  ▼
        "severity": "major"      ┌─────────────────────┐
      },                         │ Test against sample  │
      {                          │ transcripts          │
        "description": "...",    │ (dry-run mode)       │
        "type": "judgment",      └──────────┬────────────┘
        "question": "Did the               │
          agent show empathy?",             ▼
        "severity": "minor"      ┌─────────────────────┐
      }                          │ Review results       │
    ]                            │ DRAFT → PUBLISHED    │
  }                              └─────────────────────┘

Option B: Excel import
  POST /api/v1/sops/import
  Upload: SOP-template.xlsx      ┌─────────────────────┐
  ┌─────────────────────────┐    │ Parse Excel rows     │
  │ Step | Type    | Check  │    │ Map to SOP structure │
  │ Greeting | rule | kw    │───▶│ Validate             │
  │ Empathy  | judge| prompt│    │ Create as DRAFT      │
  │ Closing  | rule | kw    │    └─────────────────────┘
  └─────────────────────────┘
```

**SOP lifecycle (state machine):**

```
DRAFT ──▶ TESTING ──▶ PUBLISHED ──▶ ARCHIVED
  │          │             │
  │          ▼             │
  │      (dry-run against  │
  │       sample calls)    │
  │                        │
  └── (edit) ◀─────────────┘  (new version created,
                               old version archived)
```

- **DRAFT:** Being authored. Not used for compliance checking.
- **TESTING:** Dry-run against 5–10 sample transcripts to validate rules produce sensible results. Business user reviews outputs before publishing.
- **PUBLISHED:** Active. All incoming calls matching `call_types` are checked against this SOP.
- **ARCHIVED:** Superseded by newer version. Historical calls retain their score against this version.

**Issue Category Admin API:**

Issue categories are a first-class entity managed via API — they serve as the **single source of truth** for:
- LLM prompt taxonomy (categories loaded dynamically into the analysis prompt)
- SOP-to-call-type mapping
- Agent specialization tracking
- Reporting filters and aggregation keys

```
GET    /api/v1/categories              — List all (tree structure, filterable by active)
POST   /api/v1/categories              — Create category (admin only)
PUT    /api/v1/categories/:id          — Update name/description
DELETE /api/v1/categories/:id          — Soft-deactivate (never hard-delete — historical data references it)
GET    /api/v1/categories/:id/stats    — Call volume, avg sentiment, compliance for this category
```

**How categories flow into the AI pipeline:**
1. Active categories are fetched from DB and injected into the LLM system prompt as a structured taxonomy
2. LLM is instructed: "Classify into ONLY these categories. If none fit, use 'general.other' and flag for review"
3. LLM returns a category slug → service resolves to `issue_categories.id` via slug lookup
4. If the LLM returns an unknown slug → `requires_manual_review: true`, stores raw LLM output in `full_analysis` JSONB

**SOP Admin API endpoints:**

```
POST   /api/v1/sops                    — Create new SOP (DRAFT)
POST   /api/v1/sops/import             — Import from Excel template
GET    /api/v1/sops                    — List all SOPs (filter by status, call_type)
GET    /api/v1/sops/:id                — Get SOP details
PUT    /api/v1/sops/:id                — Update SOP (creates new version if PUBLISHED)
DELETE /api/v1/sops/:id                — Soft-delete (archive)

POST   /api/v1/sops/:id/test           — Dry-run against sample transcripts
POST   /api/v1/sops/:id/publish        — DRAFT/TESTING → PUBLISHED
POST   /api/v1/sops/:id/archive        — PUBLISHED → ARCHIVED

GET    /api/v1/sops/:id/versions       — Version history
GET    /api/v1/sops/:id/stats          — Compliance stats for this SOP (pass/fail rates)
```

**Step builder — supported check types:**

| Check Type | User Input | Internal Representation | Example |
|-----------|-----------|------------------------|---------|
| `keyword_match` | Keywords list, speaker, segment | Rule: `transcript_contains` | "Agent must say 'StreamLine' in first 60s" |
| `keyword_sequence` | Ordered keywords, speaker | Rule: `sequence_check` | "Verify identity BEFORE accessing account" |
| `timing_check` | Max time for action | Rule: `timing_within` | "Must verify identity within first 3 minutes" |
| `judgment` | Natural language question | LLM: `evaluation_prompt` | "Did agent show empathy?" |
| `sentiment_gate` | Min sentiment at call end | Rule: `sentiment_threshold` | "Customer sentiment must be >= neutral at call end" |
| `escalation_protocol` | Conditions for escalation | Hybrid: rule + LLM | "Must offer supervisor if customer asks 2+ times" |

**Excel template structure (for import):**

| Column | Description | Example |
|--------|------------|---------|
| SOP Name | Name of the procedure | "Billing Call SOP" |
| Call Types | Comma-separated categories | "billing, refund" |
| Step Order | Sequence number | 1, 2, 3... |
| Step Name | Human-readable name | "Greeting" |
| Step Type | `rule` or `judgment` | "rule" |
| Check Description | What to check | "Agent greets with company name" |
| Keywords (if rule) | Comma-separated | "StreamLine, my name is" |
| Speaker | AGENT or CUSTOMER | "AGENT" |
| Segment | When in the call | "first_60_seconds" |
| Question (if judgment) | Natural language | "Did agent show empathy?" |
| Severity | critical / major / minor | "minor" |

> **Recommendation to client:** In Phase 2, we propose building a **simple web form UI** (React) on top of this API — a drag-and-drop SOP builder where quality managers can visually assemble steps, test them, and publish. For the 8-week delivery, the API + Excel import provides full functionality without frontend development.

---

### 5.5 Data Store Layer

**Multi-store architecture — each store for what it does best:**

```
┌─────────────────────────────────────────────────────────────┐
│                     DATA STORE LAYER                         │
│                                                             │
│  ┌──────────────────┐  Purpose: Primary source of truth     │
│  │   PostgreSQL     │  for structured, relational data.     │
│  │   (RDS)          │  Calls, agents, analysis results,     │
│  │                  │  SOP definitions, compliance reports. │
│  └──────────────────┘  Supports complex JOINs for reporting.│
│                                                             │
│  ┌──────────────────┐  Purpose: Full-text search over       │
│  │  Elasticsearch   │  transcripts. Powers "search across   │
│  │  (OpenSearch)    │  all calls" feature. Aggregation      │
│  │                  │  queries for dashboards.              │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐  Purpose: Caching layer for dashboard │
│  │  Redis           │  real-time counters, rate limiting,   │
│  │  (ElastiCache)   │  session data, frequently accessed    │
│  │                  │  aggregations.                        │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐  Purpose: Blob storage for audio      │
│  │  S3              │  recordings, raw transcript files.    │
│  │                  │  Lifecycle policies for retention.    │
│  └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────┘
```

**Why PostgreSQL over MongoDB/Cassandra for the primary store:**

| Factor | PostgreSQL | MongoDB | Cassandra |
|--------|-----------|---------|-----------|
| Complex JOINs (agent + call + analysis) | Excellent | Poor (denormalize) | Very poor |
| Aggregation queries for reporting | Excellent (window functions) | Good (aggregation pipeline) | Limited |
| ACID compliance | Full | Document-level | Eventual consistency |
| JSONB for semi-structured data | Built-in, indexable | Native | Limited |
| Operational overhead | Low (RDS managed) | Medium | High |
| Cost at this scale | ~$200–400/mo | ~$300–600/mo | ~$500–1000/mo |

**Decision:** PostgreSQL handles structured + semi-structured data well via JSONB columns. At 20K records/day (~600K/month), PostgreSQL scales comfortably for years. No need for NoSQL complexity at this volume.

**Why Elasticsearch in addition to PostgreSQL:**
- Full-text search across transcripts ("find all calls where customer mentioned competitor X")
- Pre-computed aggregations for dashboard (much faster than SQL GROUP BY on large datasets)
- Near real-time indexing for live dashboards

**Why not ClickHouse/TimescaleDB:**
- At 20K calls/day, PostgreSQL with proper indexing handles time-series queries well
- ClickHouse shines at 100M+ rows — premature optimization here
- Can add TimescaleDB as a PostgreSQL extension (zero migration cost) if partitioning needs arise
- Can migrate to ClickHouse in future if analytics queries become a bottleneck

#### Aggregation Strategy: Where to Run What

Different query patterns are best served by different stores:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AGGREGATION STRATEGY                              │
│                                                                     │
│  ┌──────────────────────┐  ┌──────────────────────┐                 │
│  │ Real-Time Counters   │  │ Interactive Dashboard │                 │
│  │ (Redis)              │  │ (Elasticsearch)       │                 │
│  │                      │  │                       │                 │
│  │ • Calls processed    │  │ • Faceted filtering   │                 │
│  │   today (INCR)       │  │   (agent + date +     │                 │
│  │ • Current queue      │  │    category + sent.)  │                 │
│  │   depths             │  │ • Full-text search    │                 │
│  │ • Rolling 1-hr       │  │   across transcripts  │                 │
│  │   sentiment avg      │  │ • Top-N aggregations  │                 │
│  │ • Issue category     │  │   (top issues, worst  │                 │
│  │   counters (today)   │  │    agents, trends)    │                 │
│  │                      │  │ • Sub-second response │                 │
│  │ TTL: 5 min – 24 hr   │  │   for dashboard       │                 │
│  │ Refresh: on each     │  │                       │                 │
│  │   pipeline completion│  │ Refresh: near real-   │                 │
│  └──────────────────────┘  │   time (on ingest)    │                 │
│                            └──────────────────────┘                 │
│  ┌──────────────────────┐  ┌──────────────────────┐                 │
│  │ Scheduled Reports    │  │ Ad-Hoc Deep Queries  │                 │
│  │ (PostgreSQL MVs)     │  │ (PostgreSQL direct)   │                 │
│  │                      │  │                       │                 │
│  │ • Daily summary      │  │ • Complex JOINs       │                 │
│  │ • Agent performance  │  │   (agent + category   │                 │
│  │   (daily rollup)     │  │    + compliance +     │                 │
│  │ • Issue trends       │  │    sentiment)         │                 │
│  │   (daily rollup)     │  │ • Window functions    │                 │
│  │ • Excel export data  │  │ • Custom date ranges  │                 │
│  │                      │  │ • One-off analysis    │                 │
│  │ Refresh: every 5 min │  │                       │                 │
│  │   (CONCURRENTLY)     │  │ Response: 100ms–2s    │                 │
│  └──────────────────────┘  │   (with proper idx)   │                 │
│                            └──────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

**Why not run everything from PostgreSQL?**
- PostgreSQL materialized views are great for **scheduled, pre-computed** aggregations
- But they're **not real-time** — there's a 5-minute refresh gap
- For interactive dashboards with multi-dimensional filtering (agent × date × category × sentiment), Elasticsearch's inverted index is **10–50x faster** than SQL GROUP BY with multiple JOINs
- Redis handles **sub-millisecond** counters that update on every pipeline completion

**Why not run everything from Elasticsearch?**
- ES lacks proper JOIN support — can't correlate agent metadata with call analysis efficiently
- ES is not ACID — not suitable as primary source of truth
- Excel export with complex business logic (compliance scoring, agent ranking) requires SQL

**Bottom line:** PostgreSQL is the source of truth. ES is the query accelerator for dashboards. Redis is the real-time counter layer. Each handles what it does best, and the system degrades gracefully (if ES is down, fall back to PostgreSQL with slower queries).

---

### 5.6 Reporting & Export Service

**Purpose:** Serve analytics data to operations/quality teams via API, with Excel export as primary output format.

**API endpoints:**

```
GET  /api/v1/reports/daily-summary?date=2026-03-28
GET  /api/v1/reports/agent-performance?agent_id=A123&from=...&to=...
GET  /api/v1/reports/issue-trends?from=...&to=...&category=billing
GET  /api/v1/reports/compliance-summary?from=...&to=...
GET  /api/v1/reports/sentiment-trends?from=...&to=...

GET  /api/v1/calls?filter[agent]=A123&filter[sentiment]=negative&filter[date]=...
GET  /api/v1/calls/:id
GET  /api/v1/calls/:id/transcript
GET  /api/v1/calls/:id/analysis
GET  /api/v1/calls/:id/compliance

POST /api/v1/exports/excel    (async — returns job_id)
GET  /api/v1/exports/:job_id  (poll for completion, download link)
```

**Excel export:**
- Async generation (large reports can take 30–60 seconds)
- Generated using `openpyxl` (Python) or `exceljs` (Node)
- Multiple sheets: Summary, Call Details, Agent Performance, Compliance, Trends
- Stored in S3 with pre-signed download URL (expires in 24h)
- Configurable filters: date range, agent, issue type, sentiment, compliance status

**Dashboard data:**
- Pre-computed aggregations stored in Redis (refreshed every 5 minutes)
- Metrics: calls today, avg sentiment, top issues, compliance rate, processing backlog
- Historical trends: daily/weekly/monthly aggregations in PostgreSQL materialized views

---

### 5.7 Notification & Alerting Service

**Purpose:** Proactive alerting when anomalies or compliance violations are detected.

**Alert types:**

| Alert | Trigger | Channel |
|-------|---------|---------|
| Critical SOP violation | Any `critical` severity violation | Email + Slack (immediate) |
| Issue spike | Issue category volume > 2x rolling 7-day average | Slack + Dashboard |
| Sentiment drop | Average sentiment drops > 0.3 in 1-hour window | Slack + Dashboard |
| Agent performance | Agent compliance score < 60% over last 10 calls | Email to supervisor |
| Processing backlog | Queue depth > 500 or processing delay > 30 min | PagerDuty / Ops alert |
| System health | Service down, GPU utilization > 90%, error rate > 5% | PagerDuty |

**Implementation:**
- Runs as a lightweight background worker
- Checks Redis counters and recent data at configurable intervals (1–5 min)
- De-duplicates alerts (don't re-fire within cooldown window)
- Supports Slack webhook, email (SES), and generic webhook for extensibility

---

### 5.8 API Gateway & Auth

**Purpose:** Single entry point for all client-facing API requests.

**Approach:** Use AWS API Gateway or Kong/NGINX as reverse proxy.

**Features:**
- JWT-based authentication (integrate with client's existing identity provider)
- Role-based access control (admin, supervisor, analyst, viewer)
- Rate limiting (100 req/min per user for standard, 1000 for batch exports)
- Request logging and audit trail
- API versioning via URL prefix (`/api/v1/...`)
- CORS configuration for web dashboard

---

## 6. Data Flow & Pipeline Architecture

### 6.1 Message Queue Design

**Choice: RabbitMQ** (or AWS SQS for fully managed)

**Why RabbitMQ over Kafka at this scale:**
- 20K messages/day is trivially small for either — Kafka's strength is millions/second
- RabbitMQ's per-message acknowledgment model is better for task queues
- Simpler operations, lower overhead
- If already on AWS and want zero-ops: SQS is equivalent and costs ~$5/mo at this volume

**Queue topology:**

```
┌─────────────────────────────────────────────────────────────┐
│                     QUEUE TOPOLOGY                           │
│                                                             │
│  transcription-queue ──── priority: normal                  │
│       ├── consumer group: transcription-workers (3-5)       │
│       └── DLQ: transcription-dlq (retry exhausted)          │
│                                                             │
│  analysis-queue ────────── priority: normal                  │
│       ├── consumer group: analysis-workers (5-10)           │
│       └── DLQ: analysis-dlq                                 │
│                                                             │
│  compliance-queue ──────── priority: normal                  │
│       ├── consumer group: compliance-workers (3-5)          │
│       └── DLQ: compliance-dlq                               │
│                                                             │
│  storage-queue ─────────── priority: normal                  │
│       ├── consumer group: storage-workers (2-3)             │
│       └── DLQ: storage-dlq                                  │
│                                                             │
│  notification-queue ────── priority: high                    │
│       ├── consumer group: notification-workers (2)          │
│       └── DLQ: notification-dlq                             │
│                                                             │
│  export-queue ──────────── priority: low                     │
│       ├── consumer group: export-workers (2)                │
│       └── DLQ: export-dlq                                   │
│                                                             │
│  reprocessing-queue ────── manual trigger for re-analysis    │
│       └── feeds into analysis-queue                         │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Message Schema

Every queue message follows a standard envelope:

```json
{
  "message_id": "uuid-v4",
  "call_id": "CALL-20260328-00142",
  "timestamp": "2026-03-28T14:32:00Z",
  "source_service": "ingestion-service",
  "attempt": 1,
  "max_attempts": 3,
  "payload": {
    "audio_s3_key": "recordings/2026/03/28/CALL-20260328-00142.ogg",
    "metadata": {
      "agent_id": "A-1042",
      "duration_seconds": 385
    }
  }
}
```

### 6.3 Pipeline State Machine

Each call progresses through a state machine tracked in PostgreSQL:

```
RECEIVED → QUEUED → TRANSCRIBING → TRANSCRIBED → PII_REDACTION → ANALYZING → ANALYZED
                                                                                  │
                                                                                  ▼
                                                                           COMPLIANCE_CHECK
                                                                                  │
                                                                                  ▼
                                                                             COMPLETED

Any stage can transition to:
  → FAILED (after 3 retries exhausted — terminal, stored in DLQ)
  → MANUAL_REVIEW (low confidence or flagged — needs human review)
```

**Why sequential (not parallel) for Analysis → Compliance:**
- The SOP Compliance Engine needs the `issue_category_id` from the AI Analysis output to look up the correct SOP via `sop_category_mappings`
- A billing call gets checked against `SOP-BILLING-001`; a service outage call gets `SOP-OUTAGE-001` — this mapping requires the issue to be classified first
- Running them in parallel would require either: (a) checking against ALL SOPs (wasteful, ~5x more LLM cost), or (b) a two-pass approach (classify first, then comply) which is effectively sequential anyway

---

## 7. Database Schema Design

### 7.1 PostgreSQL Schema

```sql
-- ============================================================
-- REFERENCE / LOOKUP TABLES (Single Source of Truth)
-- ============================================================

-- Hierarchical issue categories: parent_id enables tree structure
-- e.g., "billing" → "billing.duplicate_charge", "billing.refund_request"
-- Categories are managed via Admin API and loaded into LLM prompts dynamically
CREATE TABLE issue_categories (
    id              SERIAL PRIMARY KEY,
    slug            VARCHAR(100) UNIQUE NOT NULL,    -- "billing.duplicate_charge" (dot-notation)
    name            VARCHAR(255) NOT NULL,           -- "Duplicate Charge"
    parent_id       INTEGER REFERENCES issue_categories(id),  -- NULL = top-level category
    description     TEXT,                            -- Shown in reports, used in LLM prompt
    is_active       BOOLEAN DEFAULT true,
    display_order   INTEGER DEFAULT 0,               -- For UI ordering
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_issue_cat_parent ON issue_categories(parent_id);
CREATE INDEX idx_issue_cat_slug ON issue_categories(slug);
CREATE INDEX idx_issue_cat_active ON issue_categories(is_active);

-- Seed example (actual categories to be defined with client in Week 1):
-- INSERT INTO issue_categories (slug, name, parent_id) VALUES
--   ('billing', 'Billing', NULL),
--   ('billing.duplicate_charge', 'Duplicate Charge', 1),
--   ('billing.refund_request', 'Refund Request', 1),
--   ('service', 'Service', NULL),
--   ('service.outage_report', 'Outage Report', 4),
--   ...etc

-- ============================================================
-- CORE TABLES
-- ============================================================

CREATE TABLE agents (
    id              VARCHAR(32) PRIMARY KEY,        -- e.g., "A-1042"
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255),
    team            VARCHAR(100),
    role            VARCHAR(50),                    -- "agent", "senior_agent", "supervisor"
    active          BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Agent specializations: which issue categories an agent is trained/assigned to handle
-- Used for reporting (is the right agent handling the right call type?)
CREATE TABLE agent_specializations (
    agent_id        VARCHAR(32) REFERENCES agents(id),
    category_id     INTEGER REFERENCES issue_categories(id),
    proficiency     VARCHAR(20) DEFAULT 'standard',  -- "trainee", "standard", "expert"
    assigned_at     TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (agent_id, category_id)
);

CREATE TABLE calls (
    id              VARCHAR(64) PRIMARY KEY,        -- e.g., "CALL-20260328-00142"
    agent_id        VARCHAR(32) REFERENCES agents(id),
    customer_id     VARCHAR(64),                    -- optional, if available
    recording_url   TEXT NOT NULL,                   -- S3 key
    duration_seconds INTEGER,
    call_start_time TIMESTAMPTZ NOT NULL,
    call_end_time   TIMESTAMPTZ,
    status          VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
        -- RECEIVED, QUEUED, TRANSCRIBING, TRANSCRIBED, ANALYZING,
        -- ANALYZED, COMPLIANCE_CHECK, COMPLETED, FAILED, MANUAL_REVIEW
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0,
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_calls_agent_id ON calls(agent_id);
CREATE INDEX idx_calls_status ON calls(status);
CREATE INDEX idx_calls_start_time ON calls(call_start_time);
CREATE INDEX idx_calls_agent_date ON calls(agent_id, call_start_time);

-- ============================================================
-- TRANSCRIPTION
-- ============================================================

CREATE TABLE transcripts (
    id              SERIAL PRIMARY KEY,
    call_id         VARCHAR(64) UNIQUE REFERENCES calls(id),
    full_text       TEXT NOT NULL,
    language        VARCHAR(10) DEFAULT 'en',
    overall_confidence FLOAT,
    word_count      INTEGER,
    transcript_s3_key TEXT,                         -- full JSON transcript in S3
    model_used      VARCHAR(50),                    -- "faster-whisper-large-v3"
    processing_time_ms INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Segments stored as JSONB array for flexibility
-- (detailed segments with timestamps available in S3 JSON)
-- Only summary stored in DB for query performance

-- ============================================================
-- AI ANALYSIS RESULTS
-- ============================================================

CREATE TABLE analysis_results (
    id                  SERIAL PRIMARY KEY,
    call_id             VARCHAR(64) UNIQUE REFERENCES calls(id),
    model_used          VARCHAR(50),                -- "gpt-4o-mini", "gpt-4o"
    processing_time_ms  INTEGER,

    -- Issue (FK to issue_categories — single source of truth)
    issue_category_id   INTEGER REFERENCES issue_categories(id),  -- top-level: "billing"
    issue_sub_category_id INTEGER REFERENCES issue_categories(id), -- sub: "billing.duplicate_charge"
    issue_description   TEXT,
    issue_confidence    FLOAT,

    -- Resolution
    resolution_status   VARCHAR(50),                -- "resolved", "unresolved", "escalated", "partial"
    resolution_action   VARCHAR(100),
    resolution_description TEXT,
    resolution_confidence FLOAT,

    -- Sentiment
    sentiment_overall   VARCHAR(30),                -- "positive", "negative", "neutral", "mixed"
    sentiment_score     FLOAT,                      -- -1.0 to 1.0
    sentiment_start     VARCHAR(30),
    sentiment_end       VARCHAR(30),
    sentiment_trajectory VARCHAR(30),               -- "improving", "worsening", "stable"
    sentiment_segments  JSONB,                      -- array of per-segment sentiments

    -- Themes and pain points
    themes              TEXT[],                     -- PostgreSQL array
    pain_points         TEXT[],

    -- Flags
    escalation_detected BOOLEAN DEFAULT false,
    requires_manual_review BOOLEAN DEFAULT false,
    incomplete_input    BOOLEAN DEFAULT false,
    low_confidence_fields TEXT[],

    -- Full analysis JSON (superset of above columns)
    full_analysis       JSONB,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_analysis_issue_cat ON analysis_results(issue_category_id);
CREATE INDEX idx_analysis_issue_sub ON analysis_results(issue_sub_category_id);
CREATE INDEX idx_analysis_sentiment ON analysis_results(sentiment_overall);
CREATE INDEX idx_analysis_resolution ON analysis_results(resolution_status);
CREATE INDEX idx_analysis_themes ON analysis_results USING GIN(themes);
CREATE INDEX idx_analysis_created ON analysis_results(created_at);

-- ============================================================
-- SOP DEFINITIONS
-- ============================================================

CREATE TABLE sop_definitions (
    id              VARCHAR(64) PRIMARY KEY,        -- "SOP-BILLING-001"
    version         VARCHAR(20) NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    status          VARCHAR(20) DEFAULT 'draft',    -- draft, testing, published, archived
    steps           JSONB NOT NULL,                  -- array of SOP steps (rule/llm_judgment)
    effective_from  DATE NOT NULL,
    effective_to    DATE,                            -- NULL = currently active
    is_active       BOOLEAN DEFAULT true,
    created_by      VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(id, version)
);

-- Junction table: SOP ↔ Issue Categories (many-to-many)
-- An SOP can apply to multiple issue categories, and a category can have multiple SOPs
CREATE TABLE sop_category_mappings (
    sop_id          VARCHAR(64) REFERENCES sop_definitions(id),
    category_id     INTEGER REFERENCES issue_categories(id),
    PRIMARY KEY (sop_id, category_id)
);

CREATE INDEX idx_sop_active ON sop_definitions(is_active);
CREATE INDEX idx_sop_status ON sop_definitions(status);
CREATE INDEX idx_sop_cat_map_cat ON sop_category_mappings(category_id);

-- ============================================================
-- COMPLIANCE RESULTS
-- ============================================================

CREATE TABLE compliance_results (
    id                      SERIAL PRIMARY KEY,
    call_id                 VARCHAR(64) REFERENCES calls(id),
    sop_id                  VARCHAR(64),
    sop_version             VARCHAR(20),
    overall_score           FLOAT,                  -- 0.0 to 1.0
    status                  VARCHAR(30),            -- "compliant", "partial_compliance", "non_compliant"
    checks                  JSONB NOT NULL,         -- array of individual check results
    violation_count_critical INTEGER DEFAULT 0,
    violation_count_major   INTEGER DEFAULT 0,
    violation_count_minor   INTEGER DEFAULT 0,
    requires_supervisor_review BOOLEAN DEFAULT false,
    created_at              TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(call_id, sop_id)
);

CREATE INDEX idx_compliance_call ON compliance_results(call_id);
CREATE INDEX idx_compliance_score ON compliance_results(overall_score);
CREATE INDEX idx_compliance_status ON compliance_results(status);
CREATE INDEX idx_compliance_created ON compliance_results(created_at);

-- ============================================================
-- REPORTING MATERIALIZED VIEWS
-- ============================================================

-- Daily summary (refreshed every 5 min during business hours)
CREATE MATERIALIZED VIEW mv_daily_summary AS
SELECT
    DATE(c.call_start_time) as call_date,
    COUNT(*) as total_calls,
    COUNT(*) FILTER (WHERE c.status = 'COMPLETED') as processed_calls,
    AVG(ar.sentiment_score) as avg_sentiment,
    COUNT(*) FILTER (WHERE ar.resolution_status = 'resolved') as resolved_count,
    COUNT(*) FILTER (WHERE ar.resolution_status = 'unresolved') as unresolved_count,
    COUNT(*) FILTER (WHERE ar.escalation_detected) as escalation_count,
    AVG(cr.overall_score) as avg_compliance_score,
    COUNT(*) FILTER (WHERE cr.status = 'non_compliant') as non_compliant_count
FROM calls c
LEFT JOIN analysis_results ar ON ar.call_id = c.id
LEFT JOIN compliance_results cr ON cr.call_id = c.id
GROUP BY DATE(c.call_start_time);

-- Issue category trends (joins to issue_categories for readable names)
CREATE MATERIALIZED VIEW mv_issue_trends AS
SELECT
    DATE(c.call_start_time) as call_date,
    ic.slug as issue_category,
    ic.name as issue_category_name,
    isc.slug as issue_sub_category,
    isc.name as issue_sub_category_name,
    COUNT(*) as call_count,
    AVG(ar.sentiment_score) as avg_sentiment,
    AVG(ar.issue_confidence) as avg_confidence
FROM calls c
JOIN analysis_results ar ON ar.call_id = c.id
LEFT JOIN issue_categories ic ON ic.id = ar.issue_category_id
LEFT JOIN issue_categories isc ON isc.id = ar.issue_sub_category_id
GROUP BY DATE(c.call_start_time), ic.slug, ic.name, isc.slug, isc.name;

-- Agent performance
CREATE MATERIALIZED VIEW mv_agent_performance AS
SELECT
    c.agent_id,
    DATE(c.call_start_time) as call_date,
    COUNT(*) as total_calls,
    AVG(ar.sentiment_score) as avg_sentiment,
    AVG(cr.overall_score) as avg_compliance,
    COUNT(*) FILTER (WHERE ar.resolution_status = 'resolved') as resolved_count,
    COUNT(*) FILTER (WHERE cr.requires_supervisor_review) as flagged_count
FROM calls c
LEFT JOIN analysis_results ar ON ar.call_id = c.id
LEFT JOIN compliance_results cr ON cr.call_id = c.id
GROUP BY c.agent_id, DATE(c.call_start_time);

-- ============================================================
-- EXPORT JOBS
-- ============================================================

CREATE TABLE export_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_by    VARCHAR(100),
    filters         JSONB,                          -- what filters were applied
    status          VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    file_s3_key     TEXT,                            -- S3 key for generated file
    download_url    TEXT,                            -- pre-signed URL
    expires_at      TIMESTAMPTZ,
    row_count       INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
```

### 7.2 Elasticsearch Index Mapping

```json
{
  "call_transcripts": {
    "mappings": {
      "properties": {
        "call_id":          { "type": "keyword" },
        "agent_id":         { "type": "keyword" },
        "call_date":        { "type": "date" },
        "full_text":        { "type": "text", "analyzer": "english" },
        "issue_category":   { "type": "keyword" },
        "sentiment_overall": { "type": "keyword" },
        "sentiment_score":  { "type": "float" },
        "themes":           { "type": "keyword" },
        "resolution_status": { "type": "keyword" },
        "compliance_status": { "type": "keyword" },
        "compliance_score": { "type": "float" },
        "duration_seconds": { "type": "integer" }
      }
    }
  }
}
```

Used for:
- Full-text search across all transcripts
- Faceted filtering on dashboards
- Fast aggregation queries for trend charts

### 7.3 Database Sizing & Capacity Planning

#### PostgreSQL (RDS) Sizing

**Row size estimates:**

| Table | Avg Row Size | Rows/Day | Rows/Year | Storage/Year |
|-------|-------------|----------|-----------|-------------|
| `calls` | ~350 bytes | 20,000 | 7.3M | ~2.6 GB |
| `transcripts` | ~4 KB (full_text included) | 20,000 | 7.3M | ~29 GB |
| `analysis_results` | ~2 KB (incl. JSONB) | 20,000 | 7.3M | ~14.6 GB |
| `compliance_results` | ~1.5 KB (incl. JSONB checks) | 20,000 | 7.3M | ~11 GB |
| `issue_categories` | ~200 bytes | ~50 total | ~50 | negligible |
| `agents` | ~300 bytes | ~500 total | ~500 | negligible |
| `sop_definitions` | ~2 KB | ~20 total | ~50 | negligible |
| **Indexes** | ~30% of data size | — | — | ~17 GB |
| **Total** | | | | **~74 GB/year** |

**Growth projection:**

| Timeframe | Total Data + Indexes | Recommended Instance |
|-----------|---------------------|---------------------|
| 6 months | ~40 GB | db.r6g.large (2 vCPU, 16 GB RAM) |
| 1 year | ~75 GB | db.r6g.large |
| 2 years | ~150 GB | db.r6g.xlarge (4 vCPU, 32 GB RAM) |
| 3 years | ~225 GB | db.r6g.xlarge |

**Recommended RDS configuration:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Instance class | `db.r6g.large` (start) | 2 vCPU, 16 GB RAM — comfortably handles 7M rows/year |
| Storage | 100 GB gp3, auto-scaling to 500 GB | gp3 baseline IOPS is 3,000, sufficient for our workload |
| IOPS | 3,000 baseline (gp3 included) | Peak writes: ~25 writes/sec (20K/day across 12 business hours). 3,000 IOPS is ~120x headroom |
| Multi-AZ | Yes | Automatic failover for production reliability |
| Read replicas | 1 (for reporting queries) | Offload heavy aggregation/export queries from primary |
| Backup retention | 7 days | Point-in-time recovery |
| **Monthly cost** | **$350–500** | On-demand pricing; ~$250–350 with reserved instances |

**IOPS calculation:**
- Peak pipeline throughput: ~85 calls/minute during business hours
- Each call generates ~4 writes (calls update, transcript insert, analysis insert, compliance insert) + index updates
- Peak write IOPS: ~85 × 4 = ~340 writes/min = ~6 writes/sec
- Read IOPS (dashboard/reporting): ~50–200 queries/sec during active use
- Total peak IOPS: ~250 — well within gp3's 3,000 baseline
- **No need for provisioned IOPS (io1/io2)** at this scale

**Partitioning strategy (from day 1):**

At 20K records/day, the `calls` and `analysis_results` tables will reach 7M+ rows/year. Rather than waiting for performance degradation, we partition proactively:

- **`calls`**: Range-partitioned by `call_start_time` with monthly partitions. PostgreSQL native declarative partitioning — transparent to application queries.
- **`analysis_results`**: Same monthly partitioning via `created_at`.
- **`compliance_results`**: Same monthly partitioning via `created_at`.
- **`transcripts`**: Partitioned by `created_at`; full transcript text also stored in S3 (DB stores summary only for query performance).

```sql
-- Example: calls table with monthly partitions
CREATE TABLE calls (
    ...
    call_start_time TIMESTAMPTZ NOT NULL
) PARTITION BY RANGE (call_start_time);

-- Auto-create monthly partitions (pg_partman extension or cron job)
CREATE TABLE calls_2026_03 PARTITION OF calls
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

**Benefits from day 1:**
- Query performance stays constant as data grows (partition pruning)
- Old partitions can be detached and archived independently (cheaper storage)
- `VACUUM` and index maintenance operate on smaller partition chunks
- No migration needed later — the schema supports it from the start

**Additional scaling triggers:**
- If reporting queries exceed 2s p95 → add read replica dedicated to reporting
- If storage exceeds 200 GB → upgrade to db.r6g.xlarge for more RAM (buffer pool)

#### Elasticsearch (OpenSearch) Sizing

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Instance type | `t3.medium.search` | 2 vCPU, 4 GB RAM — sufficient for our index size |
| Node count | 2 (+ 1 dedicated master for production) | High availability, replicated shards |
| Storage per node | 50 GB gp3 | 6 months of data at ~3 KB/doc = ~11 GB data + replicas |
| Index shards | 2 primary, 1 replica | Balanced write throughput and query parallelism |
| Index rollover | Monthly indices (`call_transcripts-2026-03`) | Easy retention management (delete old indices) |
| **Monthly cost** | **$150–300** | t3.medium.search × 2 nodes |

**Capacity:**
- Daily indexing: 20K documents × ~3 KB = ~60 MB/day
- Monthly index size: ~1.8 GB (before compression, ES typically compresses ~2x)
- 6-month rolling window: ~5.4 GB active data — fits comfortably in 4 GB RAM per node
- Query performance at this size: sub-100ms for most aggregations

#### Redis (ElastiCache) Sizing

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Instance type | `cache.t3.medium` | 2 vCPU, 3.09 GB RAM |
| Cluster mode | No (single node + replica) | Data fits in < 500 MB; cluster mode adds unnecessary complexity |
| Estimated memory usage | ~200–400 MB | Counters, cached aggregations, rate limiting data |
| **Monthly cost** | **$100–150** | |

**What's stored in Redis:**
- ~50 real-time counters (issue categories, sentiment buckets, queue depths): ~50 KB
- ~20 cached dashboard aggregations (JSON, TTL 5 min): ~200 KB
- Rate limiting state (per-user tokens): ~100 KB
- Session data: ~50 KB
- **Total: well under 1 GB** — smallest Redis instance is more than sufficient

#### Total Database Infrastructure Cost

| Component | Monthly Cost (on-demand) | Monthly Cost (reserved 1yr) |
|-----------|------------------------|---------------------------|
| RDS PostgreSQL (Multi-AZ) | $450 | ~$300 |
| OpenSearch (2 nodes) | $200 | ~$140 |
| ElastiCache Redis | $120 | ~$85 |
| **Total** | **$770** | **~$525** |

---

## 8. Storage & Retention Policies

### 8.1 Storage Tiers

| Data Type | Storage | Retention | Size/Record | Daily Volume | Monthly Cost Est. |
|-----------|---------|-----------|-------------|-------------|------------------|
| Audio recordings | S3 Standard → S3 IA (30d) → Glacier (90d) | 12 months | ~6 MB | ~120 GB | ~$30 (tiered) |
| Raw transcript JSON | S3 Standard | 24 months | ~8 KB | ~160 MB | ~$1 |
| PostgreSQL data | RDS | Indefinite (aggregated) | ~2 KB/call | ~40 MB | Included in RDS |
| Elasticsearch index | OpenSearch | 6 months | ~3 KB | ~60 MB | Included in cluster |
| Export files (Excel) | S3 | 30 days | ~1–50 MB | Variable | ~$2 |
| Redis cache | ElastiCache | TTL-based (5 min – 24h) | N/A | N/A | Included in instance |

### 8.2 S3 Lifecycle Policies

```
Audio recordings:
  0-30 days   → S3 Standard (frequent access for reprocessing)
  30-90 days  → S3 Infrequent Access (occasional access, 50% cheaper)
  90-365 days → S3 Glacier Instant Retrieval (archive, 68% cheaper)
  365+ days   → Delete (unless regulatory requirement extends this)

Transcripts:
  0-6 months  → S3 Standard
  6-24 months → S3 IA
  24+ months  → Delete

Export files:
  0-30 days   → S3 Standard
  30+ days    → Delete
```

### 8.3 Database Retention

- **Raw call records:** Indefinite (small footprint, ~2KB/record)
- **Analysis results:** Indefinite (small footprint, used for historical trends)
- **Compliance results:** Indefinite (regulatory/audit trail)
- **Materialized views:** Regenerated on schedule, no explicit retention needed
- **Elasticsearch:** 6-month rolling window. Older data queryable via PostgreSQL (slower but available)

### 8.4 Data Purge Process

- Automated daily job checks retention policies
- Soft-delete first (mark as `deleted`, exclude from queries)
- Hard-delete after 30-day grace period
- Audit log of all deletions

---

## 9. Technology Choices & Justification

### 9.1 Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| **Language** | Python 3.12 | Best ecosystem for AI/ML (Whisper, LLM SDKs, pyannote). Team likely has Python expertise for SDE3 role. |
| **API Framework** | FastAPI | Async-native, auto-generated OpenAPI docs, Pydantic validation, high performance |
| **Transcription** | Faster-Whisper (large-v3) | Self-hosted, 4x faster than standard Whisper, cost-effective at scale |
| **Speaker Diarization** | pyannote-audio 3.x | Best open-source diarization, integrates well with Whisper |
| **LLM (primary)** | GPT-4o-mini | Best cost/quality ratio for structured extraction at bulk volume |
| **LLM (escalation)** | GPT-4o | Higher accuracy for complex/ambiguous calls |
| **Message Queue** | RabbitMQ (or AWS SQS) | Reliable task queue semantics, simple operations at this scale |
| **Primary Database** | PostgreSQL 16 (RDS) | ACID, excellent query capabilities, JSONB support, mature ecosystem |
| **Search Engine** | Elasticsearch / OpenSearch | Full-text transcript search, dashboard aggregations |
| **Cache** | Redis 7 (ElastiCache) | Real-time counters, dashboard caching, rate limiting |
| **Object Storage** | AWS S3 | Audio recordings, transcripts, exports |
| **Container Orchestration** | ECS Fargate (or EKS) | Managed containers, auto-scaling, no server management |
| **GPU Compute** | EC2 g5.xlarge (A10G) | Best price/performance for Whisper inference |
| **Monitoring** | CloudWatch + Grafana | Metrics, logs, dashboards, alerting |
| **CI/CD** | GitHub Actions | Automated testing and deployment |
| **Excel Generation** | openpyxl | Mature Python library, supports formatting and charts |

### 9.2 Why Not...

| Alternative | Why Not |
|-------------|---------|
| Node.js / Go | Python has the best AI/ML ecosystem; Whisper, pyannote, and LLM SDKs are Python-first |
| Kafka | Overkill at 20K messages/day; adds operational complexity without proportional benefit |
| MongoDB | PostgreSQL handles both relational and semi-structured (JSONB) data; one less database to manage |
| Cassandra | Write-optimized for millions of writes/sec — we have ~20K/day; operational overhead not justified |
| ClickHouse | Excellent for analytics at 100M+ rows; at our scale PostgreSQL materialized views suffice |
| AWS Transcribe | $0.024/min = $47K/month vs ~$1.5K/month self-hosted; 30x more expensive |
| Deepgram Nova-2 | Best managed alternative ($10K–13K/mo) if GPU ops overhead is unacceptable; viable Scenario B |
| Serverless (Lambda) | GPU workloads (transcription) don't fit serverless; pipeline benefits from persistent workers |
| Self-hosted LLMs (Llama) | GPT-4o-mini at $600/mo is cheaper than GPU infra for LLM (~$3K+/mo) unless data sovereignty is required |

---

## 10. Cost Analysis

### 10.1 Monthly Cost Breakdown (at 20K calls/day)

Two scenarios presented: **cost-optimized** (self-hosted STT, spot GPUs) and **managed** (Deepgram API, no GPU ops).

#### Scenario A: Self-Hosted STT (Cost-Optimized)

| Category | Component | Specification | Monthly Cost |
|----------|-----------|--------------|-------------|
| **Compute** | GPU instances (transcription) | 3–5x g5.xlarge (A10G), spot | $1,200 – $1,600 |
| | Application services (ECS Fargate) | 2 vCPU, 4GB RAM, 8 tasks | $400 – $600 |
| **LLM APIs** | GPT-4o-mini (90% of calls) | 18K calls/day × ~5K tokens | $600 – $650 |
| | GPT-4o (10% escalation) | 2K calls/day × ~5K tokens | $130 – $150 |
| | SOP compliance (LLM judgment checks) | ~20K calls × ~2K tokens | $200 – $300 |
| **Storage** | S3 (audio, transcripts, exports) | ~4TB storage + requests | $80 – $120 |
| | RDS PostgreSQL | db.r6g.large, Multi-AZ | $350 – $500 |
| | OpenSearch (Elasticsearch) | t3.medium.search, 2 nodes | $150 – $250 |
| | ElastiCache Redis | cache.t3.medium | $100 – $150 |
| **Other** | SQS / RabbitMQ | Messaging | $10 – $50 |
| | CloudWatch + logging | Monitoring | $50 – $100 |
| | Data transfer | Network | $50 – $100 |
| **TOTAL** | | | **$3,320 – $4,470** |

#### Scenario B: Managed STT (Lower Ops, Higher Cost)

| Category | Component | Specification | Monthly Cost |
|----------|-----------|--------------|-------------|
| **STT API** | Deepgram Nova-2 | 3M min/month, enterprise tier | $8,000 – $10,000 |
| **LLM APIs** | Same as Scenario A | | $930 – $1,100 |
| **Storage** | Same as Scenario A | | $680 – $1,020 |
| **Other** | Same as Scenario A | | $110 – $250 |
| **TOTAL** | | | **$9,720 – $12,370** |

### 10.2 Total Monthly Cost Summary

| Scenario | Monthly Cost | Daily Cost | Cost/Call |
|----------|-------------|------------|----------|
| **Self-hosted, spot GPUs (recommended)** | ~$3,500 | ~$117 | **~$0.006** |
| **Self-hosted, on-demand GPUs** | ~$5,200 | ~$173 | ~$0.009 |
| **Managed (Deepgram + LLM APIs)** | ~$11,000 | ~$367 | ~$0.018 |

**Recommended: Scenario A** — at ~$0.006/call, this is extremely cost-effective. The operational overhead of GPU management is justified by ~$7K/month savings vs managed STT.

> **Client budget decision point:** If the client's monthly infrastructure budget is < $5K, go with Scenario A. If ops simplicity is prioritized and budget allows $10K+, go with Scenario B (Deepgram).

### 10.3 Scenario C: Fully Self-Hosted (Data Sovereignty)

If the client requires **no data to leave their infrastructure** (regulatory/compliance requirement), both STT and LLM can be self-hosted:

| Component | Choice | Specification | Monthly Cost |
|-----------|--------|--------------|-------------|
| STT | Faster-Whisper large-v3 | 3–5x A10G (spot) | $1,200 – $1,600 |
| LLM | Llama 3.1 70B (vLLM) | 4x A10G or 2x A100 | $3,000 – $5,800 |
| Diarization | pyannote-audio | Runs on STT GPUs | Included |
| Infrastructure | Same as Scenario A | DB, cache, queues | $1,290 – $2,070 |
| **TOTAL** | | | **$5,490 – $9,470** |

> **Trade-off:** Self-hosted LLMs (Llama 70B) are competitive with GPT-4o-mini for structured extraction but noticeably weaker on nuanced sentiment analysis and judgment-based SOP checks. Quality should be validated against golden test suite before committing.

### 10.4 Cost Optimization Strategies

1. **GPU spot instances** for transcription: 60–70% savings on GPU compute (~$1,500/mo savings)
2. **LLM Batch API**: OpenAI and Anthropic offer 50% discount for async batch processing — our pipeline qualifies since we don't need sub-second LLM responses
3. **Reserved instances** for RDS and ElastiCache: ~30% savings on always-on services
4. **S3 Intelligent-Tiering**: Automatic cost optimization for audio storage
5. **LLM caching**: Cache analysis results for near-identical transcripts (dedup repeat calls)
6. **Off-peak batch processing**: Process non-urgent re-analysis during cheaper spot pricing windows
7. **distil-whisper-large-v3**: 2x faster than large-v3 with only ~1% WER degradation — halves GPU costs if accuracy trade-off is acceptable
8. **Model distillation** (future): Fine-tune smaller LLM on GPT-4o outputs for even cheaper inference

---

## 11. Scale & Performance Analysis

### 11.1 Throughput Capacity

| Component | Capacity per Instance | Instances | Total Throughput | Headroom vs Peak |
|-----------|----------------------|-----------|-----------------|-----------------|
| Ingestion | ~200 calls/min | 2 | 400/min | ~5x |
| Transcription | ~2 calls/min | 3–5 | 6–10/min | ~1.5–2x vs peak (85/min sustained over hours, not minutes) |
| AI Analysis | ~10 calls/min (API-bound) | 5 | 50/min | ~3x |
| SOP Compliance | ~8 calls/min | 3 | 24/min | ~2x |
| Storage writes | ~100 calls/min | 2 | 200/min | ~10x |

**Bottleneck: Transcription** — This is the most resource-intensive stage. Auto-scaling GPU workers is the primary scaling lever.

### 11.2 Latency SLOs

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Ingestion → queue | < 5s (p99) | > 10s |
| Transcription | < 90s (p95) | > 180s |
| AI Analysis | < 15s (p95) | > 30s |
| SOP Compliance | < 15s (p95) | > 30s |
| End-to-end (audio → dashboard) | < 5 min (p95) | > 10 min |
| API response time | < 200ms (p95) | > 500ms |
| Excel export generation | < 60s for 10K rows | > 120s |

### 11.3 Scaling Strategy

**Horizontal scaling at each stage:**
- Ingestion: Add Fargate tasks (stateless)
- Transcription: Add GPU instances (auto-scaling group based on queue depth)
- Analysis: Add worker tasks (auto-scaling based on queue depth)
- Database: Read replicas for reporting queries; vertical scaling for writes

**Auto-scaling triggers:**
- Queue depth > 100 messages → scale up workers
- Queue depth < 10 for 10 min → scale down (but never below minimum)
- GPU utilization > 80% → add GPU instance
- API latency p95 > 300ms → add API instances

**GPU cold start mitigation:**
G5 instances take 3-5 minutes to spin up and load the Whisper model. To prevent SLO violations during traffic spikes:
- **Minimum capacity: 2 GPU instances always running** (never scale to zero), even during off-peak hours
- **AWS warm pool**: Pre-initialize stopped instances with Whisper model loaded in AMI — reduces cold start to ~60 seconds (instance start only, no model download)
- **Scheduled scaling**: Pre-scale to 3-4 instances at 8:30am before business hours begin (predictable daily pattern)
- Queue naturally buffers during the 1-3 minute scaling window — calls wait, they don't fail

---

## 12. Security & Compliance

### 12.1 PII Redaction Pipeline Stage

For a consumer services company handling billing calls, PII flows through every transcript — account numbers, dates of birth, SSNs, credit card numbers, phone numbers. This is **not optional**; PII must be redacted before transcripts reach external LLM APIs.

**PII redaction runs as a post-transcription step, before AI analysis:**

```
Transcription → PII Redaction → AI Analysis → SOP Compliance → Storage
                     │
                     ├── Detect PII patterns (regex + NER)
                     ├── Replace with tokens: [ACCOUNT_NUMBER], [SSN], [CREDIT_CARD], [DOB]
                     ├── Store mapping (original → token) in encrypted side-table
                     └── Redacted transcript sent to LLM; original stored encrypted in S3
```

**Detection approach (hybrid):**

| PII Type | Detection Method | Replacement |
|----------|-----------------|-------------|
| Credit card numbers | Regex (Luhn-validated 13-19 digit patterns) | `[CREDIT_CARD]` |
| SSN | Regex (`\d{3}-\d{2}-\d{4}`) | `[SSN]` |
| Account numbers | Regex (configurable pattern per client) | `[ACCOUNT_NUMBER]` |
| Phone numbers | Regex (10+ digits, common formats) | `[PHONE]` |
| Dates of birth | Regex + context ("date of birth", "DOB", "born on") | `[DOB]` |
| Names, addresses | SpaCy NER model (`en_core_web_sm`, ~15 MB) | `[PERSON]`, `[ADDRESS]` |

**Why this matters for LLM calls:**
- Redacted transcripts sent to OpenAI/external LLMs contain **zero raw PII**
- Even with enterprise data processing agreements, minimizing PII exposure is defense-in-depth
- The original unredacted transcript is stored **only** in S3 with KMS encryption, accessible only for audit/compliance
- Redaction adds ~1-2 seconds per call (regex is fast; SpaCy NER is lightweight)

**Implementation:** Python `presidio-analyzer` (Microsoft's open-source PII detection library) or custom regex + SpaCy pipeline. Both run on CPU with negligible resource overhead.

### 12.2 Data Security

| Concern | Mitigation |
|---------|-----------|
| Audio contains PII | Encrypt at rest (S3 SSE-KMS, RDS encryption) |
| PII in transcripts | **Redacted before LLM API calls** (see 12.1); originals encrypted in S3 |
| Data in transit | TLS 1.3 for all inter-service communication |
| LLM data leakage | Enterprise plans with data privacy agreements + PII redaction as defense-in-depth |
| Access control | RBAC via API Gateway; least-privilege IAM roles for services |
| Audit trail | All data access logged; export requests tracked in `export_jobs` table |

### 12.3 Compliance Considerations

- **Call recording consent**: Assumed handled by StreamLine's existing system (not in scope)
- **Data residency**: Deploy in client's preferred AWS region
- **GDPR/CCPA**: Support data deletion requests (cascade delete across all stores for a given customer)
- **Retention policies**: Configurable per data type (see Section 8)

---

## 13. Monitoring & Observability

### 13.1 Key Metrics Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│                  OPERATIONS DASHBOARD                        │
│                                                             │
│  Pipeline Health          │  Business Metrics               │
│  ─────────────────────    │  ────────────────────────        │
│  Calls ingested today: ▓▓ │  Top issues: Billing (34%)      │
│  Processing backlog:   ▓  │  Avg sentiment: -0.12           │
│  Avg processing time:  ▓  │  Compliance rate: 87%           │
│  Error rate:           ▓  │  Escalations today: 42          │
│  GPU utilization:      ▓  │  Unresolved calls: 1,203        │
│                           │                                 │
│  Queue Depths             │  Trend Alerts                   │
│  ──────────────           │  ────────────                   │
│  Transcription: 23        │  ⚠ Billing issues +45% vs avg  │
│  Analysis: 8              │  ⚠ Agent A-1042 compliance 52% │
│  Compliance: 5            │                                 │
│  DLQ: 2                   │                                 │
└─────────────────────────────────────────────────────────────┘
```

### 13.2 Logging Strategy

- **Structured JSON logs** (every service)
- **Correlation ID** (call_id) propagated through entire pipeline for tracing
- **Log levels**: ERROR (PagerDuty), WARN (investigate), INFO (audit), DEBUG (dev only)
- **Centralized**: CloudWatch Logs → optional export to Elasticsearch for search

### 13.3 Health Checks

Each service exposes:
- `GET /health` — basic liveness (is the process running)
- `GET /health/ready` — readiness (can it accept work — DB connected, queue accessible, GPU loaded)

---

## 14. Failure Handling & Resilience

### 14.1 Failure Modes & Recovery

| Failure | Impact | Recovery |
|---------|--------|----------|
| Single GPU instance dies | Reduced transcription throughput | Auto-scaling replaces instance; queued messages retry on other workers |
| LLM API rate limit hit | Analysis slowed | Exponential backoff + spread across multiple API keys |
| LLM API outage | Analysis blocked | Queue buffers messages; process backlog when API recovers; alert if > 30 min |
| PostgreSQL failover | Brief write interruption | Multi-AZ RDS auto-failover (< 60s); application retries |
| Queue becomes unavailable | Pipeline stalls | Ingestion stores to S3 with metadata; replay mechanism when queue recovers |
| Bad SOP definition deployed | Incorrect compliance scoring | SOP versioning; ability to reprocess calls against corrected SOP |
| Corrupted audio file | Single call fails | Validate at ingestion; reject corrupt files; log and continue |
| Whisper produces garbage | Incorrect transcript | Confidence threshold check; low-confidence transcripts flagged for manual review |

### 14.2 Retry Strategy

```
Attempt 1: Immediate
Attempt 2: 30 second delay
Attempt 3: 5 minute delay
After 3 failures: Move to Dead Letter Queue (DLQ)
DLQ: Manual review via admin dashboard; one-click reprocess
```

### 14.3 Graceful Degradation

- If transcription is backed up: new calls still queue (SQS/RabbitMQ provides buffering)
- If LLM API is down: transcription continues; analysis queues up for later
- If Elasticsearch is down: PostgreSQL serves queries (slower but functional)
- If Redis is down: dashboard is slightly slower (reads from PostgreSQL directly)

---

## 15. Project Plan — 8 Week Delivery

### 15.1 Team Structure

| Role | Person | Responsibilities |
|------|--------|-----------------|
| **SDE-3 (Tech Lead)** | You | Architecture, AI pipeline, SOP compliance engine, client communication, code reviews, deployment, delivery accountability |
| **SDE-2** | Team member | Audio ingestion, data store layer, reporting/export service, API endpoints, infrastructure setup |

### 15.2 Week-by-Week Plan

#### Week 1: Foundation & Setup
| Task | Owner | Days |
|------|-------|------|
| Finalize architecture with client, clarify open questions | SDE-3 | 1 |
| Set up AWS infrastructure (VPC, S3, RDS, queues, ECR) | SDE-2 | 3 |
| Set up CI/CD pipeline (GitHub Actions → ECS) | SDE-2 | 1 |
| Project scaffolding: monorepo structure, shared models, config | SDE-3 | 1 |
| Database schema creation and migrations setup (Alembic) | SDE-3 | 1 |
| Set up dev environment, Docker Compose for local dev | SDE-2 | 1 |
| Define API contracts (OpenAPI spec) for all services | SDE-3 | 1 |

**Milestone: Dev environment running, infra provisioned, schemas deployed, API contracts agreed.**

---

#### Week 2: Audio Ingestion + Transcription POC
| Task | Owner | Days |
|------|-------|------|
| Build Audio Ingestion Service (S3 listener, validation, queue publish) | SDE-2 | 3 |
| Build Transcription Service (Faster-Whisper integration, GPU setup) | SDE-3 | 3 |
| Speaker diarization integration (pyannote) | SDE-3 | 2 |
| Unit tests for ingestion validation logic | SDE-2 | 1 |
| Integration test: audio → S3 → ingestion → queue → transcription | Both | 1 |

**Milestone: Audio ingestion working end-to-end. Transcription producing timestamped, diarized output.**

---

#### Week 3: AI Analysis Service + Data Store
| Task | Owner | Days |
|------|-------|------|
| Build AI Analysis Service (LLM integration, prompt engineering, structured output) | SDE-3 | 4 |
| Implement tiered LLM routing (GPT-4o-mini → GPT-4o escalation) | SDE-3 | 1 |
| Build Data Store Layer (PostgreSQL writes, S3 transcript storage) | SDE-2 | 3 |
| Build pipeline state machine (call status tracking) | SDE-2 | 2 |
| Integration test: transcription → analysis → storage | Both | 1 |

**Milestone: Core pipeline working: audio → transcript → analysis → stored in DB.**

---

#### Week 4: SOP Compliance Engine + Elasticsearch
| Task | Owner | Days |
|------|-------|------|
| Build SOP Compliance Engine (rule engine + LLM judge) | SDE-3 | 4 |
| SOP definition CRUD API + YAML parser | SDE-3 | 1 |
| Set up Elasticsearch, index mapping, transcript indexing | SDE-2 | 2 |
| Build materialized view refresh jobs | SDE-2 | 1 |
| Create 3–5 sample SOP definitions for testing | SDE-3 | 1 |
| Integration test: full pipeline including compliance | Both | 1 |

**Milestone: Full pipeline working end-to-end including compliance. Transcripts searchable in ES.**

---

#### Week 5: Reporting, Export & API
| Task | Owner | Days |
|------|-------|------|
| Build Reporting API (daily summary, agent performance, trends) | SDE-2 | 3 |
| Build Excel export service (async generation, S3 upload) | SDE-2 | 2 |
| Build API Gateway layer (auth, rate limiting, routing) | SDE-2 | 2 |
| Notification service (Slack/email alerts for violations, spikes) | SDE-3 | 2 |
| Redis caching layer for dashboard data | SDE-3 | 1 |
| API documentation and client preview | SDE-3 | 1 |

**Milestone: Reporting API functional. Excel export working. Notifications firing.**

---

#### Week 6: Integration Testing + Hardening
| Task | Owner | Days |
|------|-------|------|
| End-to-end integration testing with real-world audio samples | Both | 2 |
| Error handling hardening (DLQ, retries, graceful degradation) | SDE-3 | 2 |
| Performance tuning (query optimization, caching, batch sizes) | SDE-2 | 2 |
| Fix bugs from integration testing | Both | 2 |
| Client demo #1 — show working pipeline, gather feedback | SDE-3 | 0.5 |
| Incorporate client feedback (buffer) | Both | 1.5 |

**Milestone: System stable under normal load. Client has seen a demo.**

---

#### Week 7: Load Testing + Security
| Task | Owner | Days |
|------|-------|------|
| Load testing: simulate 20K calls/day, measure throughput/latency | SDE-2 | 3 |
| Auto-scaling configuration and testing | SDE-2 | 1 |
| Security hardening (IAM, encryption verification, PII handling) | SDE-3 | 2 |
| Monitoring dashboards (Grafana/CloudWatch) | SDE-3 | 2 |
| Alerting setup (PagerDuty / CloudWatch alarms) | SDE-2 | 1 |
| Fix performance bottlenecks found in load testing | Both | 2 |

**Milestone: System tested at 1.5x peak load. Monitoring and alerting operational.**

---

#### Week 8: Production Deployment + Handover
| Task | Owner | Days |
|------|-------|------|
| Production deployment (staged rollout: 10% → 50% → 100%) | SDE-3 | 2 |
| Production smoke testing | Both | 1 |
| Documentation: runbook, architecture doc, API docs | SDE-3 | 2 |
| Client demo #2 — production walkthrough | SDE-3 | 0.5 |
| Knowledge transfer / handover documentation | Both | 1 |
| **Buffer for unexpected issues** | Both | 2 |

**Milestone: System in production processing live calls. Documentation complete.**

---

### 15.3 Critical Path

```
Week 1          Week 2          Week 3          Week 4          Week 5        Week 6-8
Infra ────────▶ Ingestion ────▶ AI Analysis ──▶ SOP Engine ──▶ Reporting ──▶ Testing
Setup           + Transcription  + Data Store    + Search        + Export       Load Test
                + Categories     + Category      + SOP Admin     + SOP Mgmt    Deploy
                  schema           → LLM flow      API             API
```

The critical path runs through: **Infra → Transcription → AI Analysis (needs categories) → SOP Compliance (needs analysis output + SOPs) → Integration Testing**. Any delay in transcription or AI analysis directly delays everything downstream.

The **admin plane** (category management, SOP management APIs) can be built in parallel by SDE-2 since it's independent CRUD work, but must be ready before SOP compliance integration testing in Week 4.

### 15.4 Risk Buffer

- Week 6 has 1.5 days explicit buffer for client feedback
- Week 8 has 2 days explicit buffer for unexpected issues
- Total buffer: ~3.5 days across the project
- If client requirements change mid-project, scope reduction options:
  - Phase 1: Core pipeline (ingestion → transcription → analysis → storage → basic reports)
  - Phase 2: SOP compliance + advanced reporting + notifications

---

## 16. Testing Strategy

### 16.1 Testing Pyramid

```
                    ┌──────────┐
                    │  E2E     │  5-10 tests
                    │  Tests   │  Full pipeline: audio → report
                    ├──────────┤
                  ┌──────────────┐
                  │ Integration  │  30-50 tests
                  │ Tests        │  Service + DB, Service + Queue
                  ├──────────────┤
                ┌──────────────────┐
                │   Unit Tests     │  150-200 tests
                │                  │  Business logic, validation,
                │                  │  prompt parsing, SOP rules
                └──────────────────┘
```

### 16.2 Test Categories

| Category | What | Tools | When |
|----------|------|-------|------|
| Unit tests | Validation logic, SOP rule engine, response parsing, schema validation | pytest, unittest.mock | Every PR |
| Integration tests | Service + PostgreSQL, Service + Queue, Service + S3 | pytest, testcontainers, docker-compose | Every PR |
| AI output tests | LLM response quality, structured output parsing, edge cases | pytest + golden test fixtures | Weekly + on prompt changes |
| Load tests | 20K calls/day simulation, queue throughput, DB performance | Locust / k6 | Week 7 |
| E2E tests | Full pipeline: upload audio → verify analysis in DB → verify report | Custom test harness | Week 6-7 |
| Security tests | API auth bypass, SQL injection, PII exposure | OWASP ZAP, manual review | Week 7 |

### 16.3 AI-Specific Testing

LLM outputs are non-deterministic, so testing requires a different approach:

- **Golden test suite**: 20–30 curated transcripts with known-correct analysis results
- **Schema compliance**: Every LLM response must parse against the Pydantic schema (hard fail if not)
- **Confidence calibration**: Verify that confidence scores correlate with actual accuracy
- **Edge cases**: Empty transcript, single-word transcript, non-English, extremely long call, profanity, multiple issues
- **Regression tests**: If a prompt change causes a previously-correct analysis to become wrong, flag it

### 16.4 Load Testing Plan

| Test | Target | Duration |
|------|--------|----------|
| Sustained throughput | 20K calls over 12 hours | 12 hours |
| Peak burst | 100 calls/min for 30 min | 30 min |
| Queue resilience | Simulate LLM API down for 1 hour, verify backlog processes after recovery | 2 hours |
| Database under load | 1M+ rows, verify query performance on reporting APIs | Benchmark |
| Auto-scaling | Ramp from 0 to peak over 30 min, verify GPU scaling | 1 hour |

---

## 17. Assumptions

### 17.1 Technical Assumptions

1. **Audio format**: Recordings are in a standard format (WAV, MP3, OGG, FLAC, or M4A), mono or stereo, sample rate >= 16kHz
2. **Metadata availability**: Each recording has accompanying metadata (call_id, agent_id, timestamp) — either in the filename, a sidecar file, or via API
3. **Language**: Primarily English. Multi-language support can be added but is not in scope for initial delivery
4. **Two-party calls**: All calls are between one customer and one agent (no conference calls)
5. **Cloud provider**: AWS is the deployment target. Architecture is portable but cost estimates are AWS-based
6. **Internet access**: GPU workers need outbound access for LLM API calls (or LLM is self-hosted)
7. **Recording delivery**: StreamLine's existing telephony system deposits recordings to S3 (or we provide an upload API)

### 17.2 Business Assumptions

1. **Issue categories**: StreamLine will provide an initial taxonomy of issue categories; we'll refine iteratively
2. **SOP documents**: StreamLine will provide existing SOP documents; we'll convert them to machine-readable format
3. **User access**: Operations and quality teams have web browser access for reports; Excel is the primary export format
4. **Data privacy**: StreamLine has consent to record and analyze calls (TCPA, local regulations handled by them)
5. **No real-time requirement**: Near real-time (< 10 min latency) is acceptable; this is not a live-call system
6. **Volume stability**: 15K–20K calls/day is the expected range for the next 12 months
7. **Working hours**: Call center operates during business hours (higher volume 9am–6pm, lower evenings/weekends)

### 17.3 Scope Boundaries

**In scope:**
- All 4 building blocks as described
- REST API for reporting
- Excel export
- Email/Slack notifications
- Admin API for SOP management

**Out of scope (unless explicitly requested):**
- Web dashboard UI (we provide the API; UI can be Phase 2 or built by another team)
- Real-time live call monitoring / streaming transcription
- Customer-facing portal
- CRM integration
- Multi-language transcription (initial release: English only)
- Custom ML model training

---

## 18. Open Questions for Client

These should be clarified before or during Week 1:

### Critical (blocks architecture)

1. **Recording delivery mechanism**: How are recordings currently stored? S3 bucket? SFTP? Direct upload API? Do recordings have a standardized naming convention?
2. **Metadata format**: What metadata accompanies each recording? Is there a companion JSON/CSV, or is it encoded in the filename, or available via an API?
3. **Issue category taxonomy**: Does StreamLine have an existing categorization of call types / issue types? If yes, provide the list. If not, do they want us to derive one?
4. **SOP documents**: In what format do current SOPs exist? Word documents? Confluence pages? How many distinct SOPs are there?
5. **Authentication**: What identity provider do the operations/quality teams use? SAML/OIDC? Okta? Azure AD?

### Important (blocks detailed design)

6. **Audio format**: What codec and sample rate are recordings in? Mono or stereo (separate channels per speaker)?
7. **Volume pattern**: What does the hourly distribution of calls look like? Is there a sharp peak or spread evenly?
8. **Retention requirements**: Are there regulatory requirements for how long recordings and analysis data must be retained?
9. **Notification channels**: What alerting channels does the ops team use? Slack? Email? PagerDuty? Teams?
10. **Budget constraints**: Is there a monthly infrastructure budget ceiling we should design within?

### Nice to know

11. **Existing infrastructure**: Does StreamLine already use AWS? What region?
12. **Historical data**: Do they want to backfill analysis for historical recordings? If so, how far back and how many?
13. **Dashboard**: Do they have an existing BI tool (Tableau, Metabase, Looker) they'd want to connect, or do they need a custom dashboard?
14. **Multi-language**: What percentage of calls are in languages other than English?
15. **Growth**: Is call volume expected to grow significantly in the next 12 months?

---

## 19. Risks & Mitigation

| # | Risk | Probability | Impact | Mitigation |
|---|------|------------|--------|-----------|
| 1 | **LLM API outage** (OpenAI/Anthropic) disrupts analysis pipeline | Medium | High | Queue buffers messages; implement fallback to secondary LLM provider; alerts on queue depth |
| 2 | **Transcription quality** varies with audio quality (background noise, accents) | High | Medium | Confidence thresholds; manual review queue for low-confidence transcripts; iterative tuning |
| 3 | **SOP definitions are ambiguous** or incomplete, leading to inaccurate compliance scoring | High | High | Iterative refinement with client; start with simple, high-confidence rules; phase in LLM judgment checks |
| 4 | **Scope creep** — client requests additional features mid-project | High | High | Clear scope document signed off in Week 1; change requests evaluated against timeline; defer to Phase 2 |
| 5 | **GPU supply/cost** — spot instances unavailable or prices spike | Medium | Medium | On-demand fallback; reserve base capacity; consider self-hosted GPU server if cloud costs spike |
| 6 | **8-week timeline is tight** for 2 engineers | High | High | Explicit buffer days; Phase 1/Phase 2 scope split ready if needed; weekly client check-ins to surface delays early |
| 7 | **LLM output quality** doesn't meet client expectations | Medium | High | Golden test suite; prompt iteration cycles; client review of sample outputs in Week 3–4 |
| 8 | **Data privacy concern** — client uncomfortable sending audio/transcripts to external LLM | Medium | High | Offer self-hosted LLM option (higher cost, lower quality); use enterprise LLM agreements with data processing guarantees |
| 9 | **Team member unavailable** (illness, emergency) | Low | High | Both engineers cross-trained on critical components; documented architecture; modular design allows independent progress |
| 10 | **Historical data backfill** requested late | Medium | Medium | Design pipeline to support batch reprocessing from day 1; backfill is just "replay recordings through the same pipeline" |

---

## 20. Future Enhancements

These are not in scope for the 8-week delivery but should be considered in architectural decisions:

### Phase 2 (Weeks 9–16, if approved)
- **Web Dashboard UI**: React-based dashboard for real-time analytics visualization
- **Agent coaching**: Automated feedback reports for individual agents based on their call analysis
- **Trend detection ML**: Time-series anomaly detection for issue spikes (beyond threshold-based alerts)
- **Multi-language support**: Add language detection and multi-language Whisper models
- **Custom fine-tuned models**: Fine-tune smaller LLM on GPT-4o outputs for lower inference cost

### Phase 3 (Future)
- **Real-time streaming analysis**: Live call monitoring with interim insights
- **CRM integration**: Push analysis results to Salesforce/Zendesk
- **Customer journey tracking**: Link calls from same customer, detect repeat callers
- **Predictive analytics**: Predict call outcomes, churn risk based on sentiment patterns
- **Voice biometrics**: Emotion detection from audio features (not just text)

---

## Appendix A: Repository Structure (Proposed)

```
vocal-analytics-service/
├── README.md
├── SYSTEM_DESIGN.md                    # This document
├── docker-compose.yml                  # Local dev environment
├── Makefile                            # Common commands
├── pyproject.toml                      # Python project config
│
├── services/
│   ├── ingestion/                      # Audio Ingestion Service
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app / worker entrypoint
│   │   ├── validators.py              # Audio validation logic
│   │   ├── s3_listener.py             # S3 event handler
│   │   └── tests/
│   │
│   ├── transcription/                  # Transcription Service
│   │   ├── __init__.py
│   │   ├── worker.py                   # Queue consumer + Whisper inference
│   │   ├── diarization.py            # Speaker diarization
│   │   ├── models.py                  # Output schemas
│   │   └── tests/
│   │
│   ├── analysis/                       # AI Analysis Service (POC target)
│   │   ├── __init__.py
│   │   ├── worker.py                   # Queue consumer
│   │   ├── llm_client.py             # LLM API abstraction
│   │   ├── prompts.py                 # Prompt templates
│   │   ├── router.py                  # Tiered model routing
│   │   ├── schemas.py                 # Pydantic output models
│   │   └── tests/
│   │
│   ├── compliance/                     # SOP Compliance Engine
│   │   ├── __init__.py
│   │   ├── worker.py                   # Queue consumer
│   │   ├── rule_engine.py            # Deterministic rule checks
│   │   ├── llm_judge.py              # LLM-based judgment checks
│   │   ├── sop_loader.py             # Load & match SOPs
│   │   └── tests/
│   │
│   ├── admin/                          # Admin / Management Plane
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app (admin APIs)
│   │   ├── routes/
│   │   │   ├── categories.py          # Issue category CRUD
│   │   │   ├── sops.py               # SOP CRUD, import, publish
│   │   │   └── agents.py             # Agent management, specializations
│   │   ├── sop_importer.py           # Excel/CSV → SOP parser
│   │   ├── sop_tester.py             # Dry-run SOP against sample transcripts
│   │   └── tests/
│   │
│   ├── reporting/                      # Reporting & Export Service
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app
│   │   ├── routes/                    # API route handlers
│   │   ├── aggregations.py           # Query builders
│   │   ├── excel_export.py           # Excel generation
│   │   └── tests/
│   │
│   └── notification/                   # Notification Service
│       ├── __init__.py
│       ├── worker.py                   # Alert evaluator
│       ├── channels.py                # Slack, email, webhook senders
│       └── tests/
│
├── shared/                             # Shared code across services
│   ├── __init__.py
│   ├── config.py                       # Configuration management
│   ├── db.py                           # Database connection
│   ├── queue.py                        # Queue client abstraction
│   ├── models.py                       # Shared Pydantic models
│   └── logging.py                      # Structured logging setup
│
├── migrations/                         # Alembic database migrations
│   ├── alembic.ini
│   └── versions/
│
├── sops/                               # Sample SOP definitions (YAML)
│   ├── SOP-BILLING-001.yaml
│   ├── SOP-OUTAGE-001.yaml
│   └── SOP-GENERAL-001.yaml
│
├── infrastructure/                     # IaC (Terraform / CloudFormation)
│   ├── main.tf
│   ├── variables.tf
│   └── modules/
│
├── scripts/                            # Utility scripts
│   ├── seed_sample_data.py
│   ├── load_test.py
│   └── reprocess_calls.py
│
└── docs/
    ├── api-spec.yaml                   # OpenAPI specification
    ├── runbook.md                      # Operations runbook
    └── architecture-diagram.png        # Exported architecture diagram
```

---

## Appendix B: Sample Issue Category Taxonomy

This is a **starter taxonomy** — to be refined with StreamLine during Week 1.

```
billing/
  ├── duplicate_charge
  ├── incorrect_amount
  ├── refund_request
  ├── payment_method_update
  ├── billing_cycle_question
  └── promo_code_issue

service/
  ├── outage_report
  ├── slow_performance
  ├── feature_not_working
  ├── connectivity_issue
  └── service_degradation

account/
  ├── plan_change
  ├── cancellation
  ├── reactivation
  ├── password_reset
  ├── profile_update
  └── account_locked

product/
  ├── how_to_use
  ├── feature_request
  ├── product_confusion
  ├── compatibility_issue
  └── setup_help

complaint/
  ├── previous_interaction
  ├── unresolved_issue
  ├── agent_behavior
  ├── policy_disagreement
  └── escalation_request

general/
  ├── information_request
  ├── feedback
  ├── compliment
  └── other
```

---

*End of System Design Document*
