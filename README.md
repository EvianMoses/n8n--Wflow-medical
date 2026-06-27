<div align="center">

# 🏥 MedAI — Intelligent Cloud Document Analyst

### Enterprise-grade, multi-modal document intelligence & semantic search for the medical domain

`n8n orchestration` · `FastAPI microservice` · `Gemini 2.5 Flash (Vision)` · `Pinecone Vector Search` · `Google Workspace`

</div>

---

## 📘 Overview

**MedAI** is a production-grade pipeline that automates the end-to-end lifecycle of clinical documents — from ingestion to intelligence to retrieval.

It watches a Google Drive folder for incoming files (PDF, DOCX, or multi-document ZIP batches), extracts text **and embedded imagery** through a dedicated **FastAPI** microservice, performs **multi-modal analysis** with **Google Gemini 2.5 Flash**, enriches every record with deterministic routing metadata, and delivers structured results to Google Sheets — complete with automated Gmail alerts, a daily executive digest, and a live operations dashboard.

Crucially, MedAI is more than a parser: every processed document is embedded and indexed in **Pinecone**, transforming a passive archive into a **semantically searchable knowledge base**. Clinicians can ask natural-language questions ("patient with severe migraines") and retrieve the most contextually relevant records — not just keyword matches.

> **Design philosophy:** low-code orchestration (n8n) for flow control and integrations, paired with a precise, testable Python service for parsing, enrichment, and vector logic.

---

## 🖼️ System Gallery

<img width="1297" height="449" alt="Screenshot 2026-06-27 142241" src="https://github.com/user-attachments/assets/20898e56-e9b5-41d8-8253-9637754dbf2a" />


<details>
<summary><b>📸 Click here to view system images (Screenshots)</b></summary>


**Live Dashboard:**
<img width="1362" height="879" alt="Screenshot 2026-06-27 140613" src="https://github.com/user-attachments/assets/ca918ce7-6cfc-4876-8ded-4dd713a9fb7d" />

**Semantic Search from the Live Dashboard:**
<img width="1243" height="563" alt="Screenshot 2026-06-27 140157" src="https://github.com/user-attachments/assets/22e142c4-db76-4ecf-8b4e-65ae2a62900d" />

**Daily Email Digest:**
<img width="2242" height="1158" alt="Pipeline detail" src="https://github.com/user-attachments/assets/2afa72a7-fa94-46fb-9fba-f4b6efab4594" />

**Email Alert** 


**Csv tracking:**
<img width="1864" height="566" alt="Email digest" src="https://github.com/user-attachments/assets/f4a52408-fa2f-43b5-8827-baf8889c6ca7" />

</details>
---

## 🏗️ Architecture

MedAI is composed of five cooperating layers, each with a single, well-defined responsibility.

| Layer | Technology | Responsibility |
| --- | --- | --- |
| **Orchestration** | n8n | Triggers, conditional branching, retries, batch handling, delivery |
| **Extraction & Logic** | FastAPI · PyMuPDF · python-docx | Text/image extraction and deterministic metadata enrichment |
| **Intelligence** | Google Gemini 2.5 Flash (multi-modal) | Summarization, classification, sentiment, entity extraction |
| **Semantic Search** | Google `gemini-embedding-001` · Pinecone | 768-dim embedding generation and cosine similarity retrieval |
| **Persistence & Presentation** | Google Sheets · Drive · Gmail · HTML/JS | Logging, archival, alerting, visualization, search UI |

The FastAPI service is **stateless** and runs locally. n8n reaches it at `http://host.docker.internal:8000` (when containerized); the browser dashboard calls it at `http://localhost:8000`.

### Pipeline Flow

```
Google Drive (incoming_docs)
        │  new file (polled every minute)
        ▼
   Download file ──► ZIP? ──yes──► Decompress ──► Split into individual documents
        │                                              │
        no ◄────────────────────────────────────────── ┘
        ▼
   Loop Over Items
        ├─► POST /extract   (FastAPI: text + up to 3 Base64 images)
        │        ▼
        │   Gemini 2.5 Flash (multi-modal generateContent → strict JSON)
        │        ▼
        │   POST /enrich    (FastAPI: department, sensitivity, routing tag, IDs)
        │        ▼
        │   Append row ──► Google Sheet (Medic_doc_log)
        │        ├─► Generate Markdown + JSON ──► Upload to output_docs
        │        ├─► POST /vectorize ──► Pinecone (semantic index)
        │        └─► Sensitivity gate ──► Gmail (🔴 red alert | standard summary)
        └─► Delete original from incoming_docs

Scheduled (cron):   Schedule Trigger ─► Read Sheet ─► Filter last 24h ─► Gmail HTML digest
On-demand (UI):     Dashboard search ─► POST /search ─► embed query ─► Pinecone top-k ─► ranked results
```

**Stages at a glance:** `Trigger → Extract → AI Analysis → Enrichment → Output & Alerts → Index & Search`

---

## ⭐ Core Features

### 1. Multi-Modal AI — Gemini Vision
The extraction service detects and isolates **up to 3 embedded images per PDF** (via PyMuPDF) and returns them as Base64. Within n8n, each image is appended to the Gemini request `parts` array through **`inlineData`**, so the model analyzes **visual evidence (charts, scans, diagrams) alongside the narrative text** for comprehensive, cross-referenced understanding.

```js
// Images are streamed into the Gemini request alongside the text
...($json.images || []).map(img => ({
  inlineData: { mimeType: img.mime_type, data: img.data }
}))
```

The call targets `gemini-2.5-flash:generateContent` with `temperature: 0.1` and `responseMimeType: application/json` for deterministic, schema-locked output.

### 2. Semantic Search & RAG — Vector Database
Document summaries are converted into **768-dimensional embeddings** and upserted into a **Pinecone** index (`metric=cosine`), enabling deep, **context-aware retrieval** rather than brittle keyword matching. The source text and routing metadata are stored alongside every vector, so results are self-describing and ready for downstream RAG.

```python
pinecone_index.upsert(vectors=[
    (document_id, embedding_vector, {**metadata, "text": text})
])
```

> ℹ️ **Implementation note:** embeddings are generated with Google's **`gemini-embedding-001`** model (`output_dimensionality=768`). The same model and dimensionality are used at both index and query time — a hard requirement for valid similarity scoring.

### 3. Live Interactive Dashboard
A custom HTML/JS dashboard (Chart.js) connects directly to the Google Sheets database via a **Google Apps Script** Web App, visualizing in real time:

- Total documents processed, confidential-alert count, and active departments
- A **departmental routing-distribution** bar chart
- A live activity feed of recent records
- An integrated **Semantic Medical Search** interface — natural-language queries rendered as ranked cards with a match-confidence percentage and color-coded badges (department, sensitivity, routing tag), including loading and offline-server states.

### 4. Multi-File Batch Ingestion
Advanced routing autonomously handles **`.zip` drops**: the archive is decompressed, empty/irrelevant entries are filtered out, and each contained document is processed **independently through the full pipeline** via a batching loop — with pacing between batches for stability.

### 5. Daily Email Digest
A scheduled **cron trigger** queries the database for every document processed in the **trailing 24 hours**, compiles a formatted **HTML summary report**, and dispatches it via Gmail. When there is no activity, a concise "no new documents" notice is sent instead.

### 6. Sensitivity Alerting — Automated Triage
Routing logic inspects the AI-derived `sensitivity` field. Documents flagged **`confidential`** (based on high-risk entity detection — e.g., oncology, psychiatry, HIV, STD) instantly trigger a **high-priority, red-alert email** to designated personnel; routine documents receive a standard formatted summary.

### 7. Enterprise Retry Logic
The Gemini HTTP nodes are hardened against API rate limits and transient network failures with **automated retries and a fixed 5-second backoff**, ensuring stability under load.

| Setting | Value |
| --- | --- |
| `retryOnFail` | `true` |
| `waitBetweenTries` | `5000 ms` |

---

## 🔌 The FastAPI Microservice

<table>
<thead>
<tr><th>Method</th><th>Endpoint</th><th>Purpose</th></tr>
</thead>
<tbody>
<tr><td><code>GET</code></td><td><code>/health</code></td><td>Liveness probe — <code>{"status": "ok"}</code></td></tr>
<tr><td><code>GET</code></td><td><code>/categories</code></td><td>Supported medical document categories</td></tr>
<tr><td><code>POST</code></td><td><code>/extract</code></td><td>Text + up to 3 Base64 images from an uploaded file</td></tr>
<tr><td><code>POST</code></td><td><code>/enrich</code></td><td>Convert Gemini output into routing metadata</td></tr>
<tr><td><code>POST</code></td><td><code>/sensitivity</code></td><td>Standalone sensitivity classification</td></tr>
<tr><td><code>POST</code></td><td><code>/vectorize</code></td><td>Embed a document and upsert it into Pinecone</td></tr>
<tr><td><code>POST</code></td><td><code>/search</code></td><td>Embed a query and return top-k semantic matches</td></tr>
</tbody>
</table>

**Enrichment rules** (`/enrich`) are fully deterministic and auditable:

| Output | Rule |
| --- | --- |
| `department` | `discharge_summary → Internal Medicine` · `lab_result → Laboratory` · `clinical_note → General Practice` · `prescription → Pharmacy` · else `General Admission` |
| `sensitivity` | `confidential` if high-risk terms present, else `internal` |
| `routing_tag` | `< 0.6 → escalate-to-doctor` · `< 0.8 → needs-review` · else `auto-approved` |
| `document_id` | Generated UUID |
| `processed_at` | UTC ISO-8601 timestamp |

<details>
<summary><strong>📄 Data Contracts (request / response schemas)</strong></summary>

<br>

**`/extract` → output**
```json
{
  "text": "all extracted text...",
  "images": [{ "mime_type": "image/jpeg", "data": "base64_string..." }]
}
```

**Gemini structured output → consumed by `/enrich`**
```json
{
  "summary": "2-3 sentence clinical summary",
  "classification": "lab_result",
  "sentiment": "neutral",
  "entities": { "people": [], "organizations": [], "dates": [], "medical_terms": [] },
  "action_items": [],
  "confidence_score": 0.95
}
```

**`/vectorize` → request**
```json
{
  "document_id": "uuid-or-id",
  "text": "clinical summary to embed",
  "metadata": { "department": "Laboratory", "sensitivity": "internal", "routing_tag": "auto-approved" }
}
```

**`/search` → request & response**
```json
// request
{ "query": "patient with severe migraines", "top_k": 3 }

// response
{
  "results": [
    {
      "document_id": "uuid",
      "score": 0.82,
      "text": "clinical summary...",
      "department": "Neurology",
      "sensitivity": "internal",
      "routing_tag": "auto-approved"
    }
  ]
}
```

**Google Sheet columns (`Medic_doc_log`)**
```
Document ID | Department | Sensitivity | Routing Tag | Processed At | Summary
```

</details>

---

## ✅ Prerequisites

| Requirement | Notes |
| --- | --- |
| **Python 3.10+** | For the FastAPI microservice |
| **n8n** | npm or Docker; Docker reaches the host via `host.docker.internal` |
| **Google Cloud project** | Drive, Sheets, and Gmail APIs enabled (OAuth2) |
| **Google Gemini API key** | Powers both analysis and embeddings (Google AI Studio) |
| **Pinecone account & index** | Index created with **`dimension=768`**, **`metric=cosine`** |

---

## ⚙️ Installation

### 1. Python Backend

```bash
git clone <your-repo-url>
cd medical_metadata_api

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt

uvicorn main:app --host 0.0.0.0 --port 8000
```

Verify: `GET http://localhost:8000/health` → `{"status": "ok"}`

### 2. Environment Variables

Create a git-ignored `.env` in the project root:

```ini
GEMINI_API_KEY=your_gemini_api_key
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=medical-docs
```

> ⚠️ `uvicorn --reload` watches only `.py` files — **restart the server** after editing `.env`.
> The service also injects the OS certificate store at startup (via `truststore`) so it works behind corporate TLS-inspecting proxies without disabling certificate verification.

### 3. Pinecone Index

Create an index named to match `PINECONE_INDEX_NAME`, with **`dimension=768`** and **`metric=cosine`** (to match `gemini-embedding-001` at 768 dims).

### 4. Google Workspace

1. Create Drive folders `incoming_docs` and `output_docs`.
2. Create a Google Sheet named `Medic_doc_log`.
3. Add these exact headers in row 1:
   ```
   Document ID | Department | Sensitivity | Routing Tag | Processed At | Summary
   ```

### 5. n8n Workflow

1. **Add Workflow → Import from File** → select `madical_docs_workFlow.json`.
2. Attach credentials:

   | Node | Credential |
   | --- | --- |
   | Drive Trigger / Download / Upload / Delete | Google Drive OAuth2 |
   | Append row / Get row(s) | Google Sheets OAuth2 |
   | Send a message (×3) | Gmail OAuth2 |
   | HTTP Request (gemini) | Gemini API key (header auth) |

3. Re-select your **folder IDs** and **spreadsheet**, update Gmail `sendTo` recipients, and confirm the FastAPI URLs.
4. **Save** and toggle the workflow **Active**.

### 6. Dashboard

1. In the Sheet: **Extensions → Apps Script**, add a `doGet` that returns rows as JSON, then **Deploy → Web App**.
2. In `dashboard.html`, set `API_URL` to your Web App URL (`SEARCH_API_URL` defaults to `http://localhost:8000/search`).
3. Open `dashboard.html` in a browser.

---

## 🚀 Usage

**Automated ingestion**

1. Ensure the FastAPI service is running and the n8n workflow is **Active**.
2. Drop a `.pdf`, `.docx`, or `.zip` into the `incoming_docs` Drive folder.
3. Within ~1 minute the pipeline will extract, analyze, enrich, log to Sheets, archive Markdown/JSON to `output_docs`, send the appropriate email, index the document in Pinecone, and clean up the original.
4. Review results in the Sheet, the dashboard, and your inbox; a consolidated digest arrives daily.

**Semantic search**

- From the dashboard, type a clinical query and press **Search** (or Enter). Results are ranked by confidence with department, sensitivity, and routing badges.
- Or call the API directly:

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "patient with severe migraines", "top_k": 3}'
```

---

## 📁 Project Structure

```
medical_metadata_api/
├── main.py                      # FastAPI microservice (extract · enrich · sensitivity · vectorize · search)
├── extract_pdf.py               # Standalone CLI extractor (text + Base64 images)
├── dashboard.html               # Live operations dashboard + semantic search (Chart.js)
├── madical_docs_workFlow.json   # n8n workflow definition
├── requirements.txt             # Pinned Python dependencies
├── .env                         # Secrets & configuration (git-ignored)
└── .gitignore
```

---

<div align="center">

> 🔒 **Compliance:** This system processes Protected Health Information (PHI). Treat all credentials, the `.env` file, and the `incoming_docs` / `output_docs` contents as confidential, and ensure your deployment meets the regulatory requirements applicable to your organization.

</div>
