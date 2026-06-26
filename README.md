# MedAI — Intelligent Cloud Document Analyst for the Medical Domain

MedAI is an enterprise-grade document intelligence pipeline purpose-built for clinical environments. It ingests medical files from Google Drive (including multi-file ZIP batches), extracts text and embedded imagery through a local **FastAPI** microservice, performs multi-modal analysis with **Google Gemini 2.5 Flash**, enriches the results with deterministic routing metadata, and delivers structured output to Google Sheets alongside automated Gmail alerts and a live operations dashboard.

The system is orchestrated end-to-end by an **n8n** workflow, combining low-code orchestration with a dedicated Python service for the parsing and business logic that demands precision.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Pipeline Flow](#pipeline-flow)
- [Core Features](#core-features)
- [Advanced Implementations](#advanced-implementations)
- [The FastAPI Microservice](#the-fastapi-microservice)
- [Data Contract](#data-contract)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Usage](#usage)
- [Project Structure](#project-structure)

---

## Architecture Overview

MedAI is composed of four cooperating layers:

| Layer | Technology | Responsibility |
| --- | --- | --- |
| **Orchestration** | n8n | Triggers, branching, retries, batch handling, delivery |
| **Extraction & Logic** | FastAPI + PyMuPDF + python-docx | Text/image extraction and metadata enrichment |
| **Intelligence** | Google Gemini 2.5 Flash (multi-modal) | Summarization, classification, entity extraction |
| **Persistence & Presentation** | Google Sheets, Google Drive, Gmail, HTML/JS dashboard | Logging, archival, alerting, visualization |

The FastAPI service is intentionally stateless and runs locally; n8n reaches it via `http://host.docker.internal:8000` when running inside Docker.

---

## Pipeline Flow

```
Google Drive (incoming_docs)
        │  new file (polled every minute)
        ▼
   Download file ──► ZIP? ──yes──► Decompress ──► Split into individual files
        │                                              │
        no ◄────────────────────────────────────────── ┘
        ▼
   Loop Over Items
        ├─► POST /extract  (FastAPI: text + up to 3 base64 images)
        │        ▼
        │   Gemini 2.5 Flash  (multi-modal generateContent, JSON output)
        │        ▼
        │   POST /enrich  (FastAPI: department, sensitivity, routing tag, IDs)
        │        ▼
        │   Append row ──► Google Sheet (Medic_doc_log)
        │        ├─► Generate Markdown + JSON ──► Upload to output_docs
        │        └─► Sensitivity gate ──► Gmail (red alert  |  standard summary)
        └─► Delete original from incoming_docs

Scheduled (independent):
   Schedule Trigger ──► Read Sheet ──► Filter last 24h ──► Gmail HTML digest
```

**Stages at a glance:** Trigger → Extract → AI Analysis → Metadata Enrichment → Output & Alerts.

---

## Core Features

- **Multi-modal AI analysis.** Gemini 2.5 Flash analyzes document text alongside embedded images, cross-referencing visual data (charts, scans, diagrams) with the narrative text.
- **Deterministic metadata enrichment.** A Python service maps each document to a hospital department, derives a sensitivity level, and assigns a routing tag — logic that stays auditable and outside the LLM.
- **Cloud logging.** Every processed document is appended as a structured row to a Google Sheet (`Medic_doc_log`).
- **Standardized archival.** Human-readable Markdown and machine-readable JSON reports are generated per document and uploaded to a Drive `output_docs` folder.
- **Conditional alerting.** Confidential documents trigger a high-priority red-alert email; routine documents receive a formatted summary email.
- **Self-cleaning intake.** The original file is removed from `incoming_docs` after processing to keep the watched folder clean.

---

## Advanced Implementations

The following capabilities were explicitly designed and verified in the shipped workflow.

### Gemini Vision (Multi-Modal)
The `/extract` endpoint isolates up to **three** embedded images per PDF using PyMuPDF and returns them as Base64. The n8n Gemini node dynamically appends each image to the request `parts` array via `inlineData`, so the model reasons over text and imagery together:

```js
...($json.images || []).map(img => ({
  inlineData: { mimeType: img.mime_type, data: img.data }
}))
```

The call targets `gemini-2.5-flash:generateContent` with `temperature: 0.1` and `responseMimeType: application/json` to force deterministic, strictly-structured output.

### Retry Logic & Rate-Limit Resilience
The Gemini HTTP Request node is hardened for production traffic with automatic retries and a fixed back-off, absorbing transient `429`/`5xx` responses from the Gemini API:

| Setting | Value |
| --- | --- |
| `retryOnFail` | `true` |
| `waitBetweenTries` | `5000 ms` |

### Sensitivity Alerting
After enrichment, an **IF** node inspects the `Sensitivity` field. When it equals `confidential`, the workflow dispatches an urgent, red-flagged email to designated personnel; otherwise it sends a standard summary. Sensitivity is computed in Python by scanning extracted entities for high-risk terms (e.g., `hiv`, `psychiatry`, `oncology`, `std`).

### Multi-File Batch Processing
An **IF** node detects `.zip` uploads. ZIP archives are decompressed, split into individual binary items, and processed one-by-one through a batching loop — each contained document flows through the full extract → analyze → enrich → deliver pipeline independently, with a short pacing delay between batches for stability.

### Daily Email Digest
An independent **Schedule Trigger** reads the Google Sheet, filters rows whose `Processed At` timestamp falls within the last 24 hours, and renders an aggregated HTML table that is emailed as a daily digest. If no documents were processed, a friendly "no activity" message is sent instead.

### Live Dashboard
`dashboard.html` is a self-contained HTML/JS client (Chart.js) that fetches the Google Sheet data through a Google Apps Script Web App and renders, in real time:

- Total documents processed
- Confidential alert count
- Active department count
- A departmental routing-distribution bar chart
- A live feed of recent document logs

---

## The FastAPI Microservice

`main.py` exposes the following endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe — returns `{"status": "ok"}` |
| `GET` | `/categories` | Lists supported medical document categories |
| `POST` | `/extract` | Extracts text + up to 3 Base64 images from an uploaded file |
| `POST` | `/enrich` | Converts Gemini output into routing metadata |
| `POST` | `/sensitivity` | Standalone sensitivity classification |

**Extraction routing.** `/extract` accepts `multipart/form-data`. `.docx` files are parsed with `python-docx` (text only); everything else (`.pdf` or unknown) is parsed with PyMuPDF (text + images). All failures are caught and returned as `{"error": "..."}` so the pipeline never receives a hard `500`.

**Enrichment logic.** `/enrich` deterministically derives:

| Output | Rule |
| --- | --- |
| `department` | `discharge_summary → Internal Medicine`, `lab_result → Laboratory`, `clinical_note → General Practice`, `prescription → Pharmacy`, else `General Admission` |
| `sensitivity` | `confidential` if sensitive medical terms are present, else `internal` |
| `routing_tag` | `< 0.6 → escalate-to-doctor`, `< 0.8 → needs-review`, else `auto-approved` |
| `document_id` | Generated UUID |
| `processed_at` | UTC ISO-8601 timestamp |

---

## Data Contract

**Extraction output (`/extract`):**

```json
{
  "text": "all extracted text...",
  "images": [
    { "mime_type": "image/jpeg", "data": "base64_string..." }
  ]
}
```

**Gemini structured output (consumed by `/enrich`):**

```json
{
  "summary": "2-3 sentence clinical summary",
  "classification": "lab_result",
  "sentiment": "neutral",
  "entities": {
    "people": [], "organizations": [], "dates": [], "medical_terms": []
  },
  "action_items": [],
  "confidence_score": 0.95
}
```

**Google Sheet columns (`Medic_doc_log`):**

```
Document ID | Department | Sensitivity | Routing Tag | Processed At | Summary
```

---

## Prerequisites

- **Python 3.10+**
- **n8n** (npm or Docker). If running n8n in Docker, the service is reachable at `host.docker.internal`; ensure outbound access to the host is permitted.
- **Google Cloud project** with the Drive, Sheets, and Gmail APIs enabled (for OAuth2 credentials).
- **Google Gemini API key** (Google AI Studio).

---

## Installation & Setup

### Step 1 — Python Backend

```bash
# Clone and enter the project
git clone <your-repo-url>
cd medical_metadata_api

# Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Launch the service (must stay running for the pipeline to work)
uvicorn main:app --host 0.0.0.0 --port 8000
```

Verify with `GET http://localhost:8000/health` → `{"status": "ok"}`.

### Step 2 — Google Workspace

1. Create two Google Drive folders: `incoming_docs` and `output_docs`.
2. Create a Google Sheet named `Medic_doc_log`.
3. Add these exact headers in row 1:

   ```
   Document ID | Department | Sensitivity | Routing Tag | Processed At | Summary
   ```

### Step 3 — Import & Configure the n8n Workflow

1. In n8n: **Add Workflow → Import from File** and select `madical_docs_workFlow.json`.
2. Configure credentials on the flagged nodes:

   | Node | Credential |
   | --- | --- |
   | Google Drive Trigger / Download / Upload / Delete | Google Drive OAuth2 |
   | Append row / Get row(s) | Google Sheets OAuth2 |
   | Send a message (×3) | Gmail OAuth2 |
   | HTTP Request (gemini) | Gemini API key (header auth) |

3. Re-select your own **folder IDs** (`incoming_docs`, `output_docs`) and **spreadsheet** in the relevant nodes.
4. Update the `sendTo` recipient(s) in the three Gmail nodes.
5. Confirm the two `HTTP Request` nodes point to your FastAPI host (`http://host.docker.internal:8000/extract` and `/enrich`).
6. **Save** and toggle the workflow to **Active**.

### Step 4 — Gemini API Key

1. Generate a key in Google AI Studio.
2. Add it to the **HTTP Request (gemini)** node's header-auth credential.
3. The endpoint and model (`gemini-2.5-flash:generateContent`) are preconfigured in the imported workflow.

### Step 5 — Dashboard (Optional)

1. In the Google Sheet: **Extensions → Apps Script**.
2. Add a `doGet` function that returns the sheet rows as JSON, then **Deploy → Web App** (access: anyone).
3. In `dashboard.html`, set `API_URL` to your Apps Script Web App URL.
4. Open `dashboard.html` in a browser to view live metrics.

---

## Usage

1. Ensure the FastAPI service is running and the n8n workflow is **Active**.
2. Drop a `.pdf` or `.docx` file — or a `.zip` containing several documents — into the `incoming_docs` Drive folder.
3. The pipeline triggers automatically (Drive is polled every minute) and will:
   - extract content, analyze it with Gemini, and enrich the metadata;
   - append a row to `Medic_doc_log`;
   - upload Markdown + JSON reports to `output_docs`;
   - send a summary or confidential-alert email;
   - delete the original from `incoming_docs`.
4. Review results in the Google Sheet, the dashboard, and your inbox. A consolidated digest arrives on the daily schedule.

---

## Project Structure

```
medical_metadata_api/
├── main.py                      # FastAPI microservice (extract / enrich / sensitivity)
├── extract_pdf.py               # Standalone CLI extractor (text + base64 images)
├── dashboard.html               # Live operations dashboard (Chart.js)
├── madical_docs_workFlow.json   # n8n workflow definition
├── requirements.txt             # Python dependencies (pinned)
├── .env                         # Secrets & configuration (not committed)
└── .gitignore
```

---

> **Compliance note:** This system processes protected health information (PHI). Treat all credentials, the `.env` file, and the `incoming_docs` / `output_docs` content as confidential, and ensure your deployment meets the regulatory requirements applicable to your organization.
