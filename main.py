import os
import uuid, datetime, base64, io
from pathlib import Path

# 0. Trust the OS certificate store (Windows/macOS/Linux) for all TLS connections.
#    Required behind corporate TLS-inspecting proxies that inject a self-signed root CA,
#    otherwise Pinecone (urllib3) and Gemini (httpx) fail with CERTIFICATE_VERIFY_FAILED.
#    Must run before any HTTPS client builds its SSL context.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception as e:
    print(f"truststore injection skipped: {e}")

from dotenv import load_dotenv

# 1. Load environment variables at the very beginning, before anything else reads them.
#    Resolve the .env by absolute path (next to this file) so it loads regardless of the
#    process working directory (e.g. under `uvicorn --reload`), and override any stale
#    OS-level variables so the .env is the single source of truth.
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

import fitz  # PyMuPDF
import docx  # python-docx
from google import genai
from google.genai import types
from pinecone import Pinecone
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Environment variables ---
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

app = FastAPI()

# Enable CORS so the local HTML dashboard can call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global clients (defined at module scope so endpoints can reference them) ---
ai_client = None
pinecone_index = None

# 2. אתחול מודל ההטמעות של גוגל (google-genai SDK)
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Gemini init failed: {e}")
else:
    print("Warning: GEMINI_API_KEY not found.")

# 3. אתחול חיבור ל-Pinecone
if PINECONE_API_KEY and PINECONE_INDEX_NAME:
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    except Exception as e:
        print(f"Pinecone init failed: {e}")
else:
    print("Warning: Pinecone configuration missing.")

# Maximum number of images to extract from an uploaded PDF.
MAX_IMAGES = 3

# המבנה שאנחנו מצפים לקבל מ-n8n (אחרי ש-Gemini ניתח את המסמך)
class GeminiResult(BaseModel):
    classification: str
    sentiment: str
    confidence_score: float
    entities: dict

# מבנה הבקשה לווקטוריזציה (חיפוש סמנטי)
class VectorizeRequest(BaseModel):
    document_id: str
    text: str
    metadata: dict

# מבנה הבקשה לחיפוש סמנטי
class SearchRequest(BaseModel):
    query: str
    top_k: int = 3

@app.get('/health')
def health():
    """Health check endpoint — must return {'status': 'ok'}"""
    return {"status": "ok"}

@app.get('/categories')
def categories():
    """Returns the list of available document categories (Medical Domain)"""
    return {
        "categories": ["discharge_summary", "lab_result", "clinical_note", "prescription"]
    }

@app.post('/sensitivity')
def check_sensitivity(data: GeminiResult):
    """Classifies document sensitivity based on medical keywords in entities"""
    entities_str = str(data.entities).lower()
    # אם נמצאות מחלות רגישות או תרופות מסוימות, נסווג כסודי
    if any(keyword in entities_str for keyword in ['hiv', 'psychiatry', 'oncology', 'std']):
        return {"sensitivity": "confidential"}
    return {"sensitivity": "internal"}

@app.post('/enrich')
def enrich(data: GeminiResult):
    """Accepts Gemini JSON output, returns enriched medical metadata"""
    
    # 1. מיפוי סיווג המסמך למחלקה רפואית מתאימה
    dept_map = {
        'discharge_summary': 'Internal Medicine',
        'lab_result': 'Laboratory',
        'clinical_note': 'General Practice',
        'prescription': 'Pharmacy'
    }
    department = dept_map.get(data.classification, 'General Admission')
    
    # 2. קביעת רגישות (שימוש בלוגיקה מהנתיב הקודם)
    entities_str = str(data.entities).lower()
    sensitivity = 'confidential' if any(k in entities_str for k in ['hiv', 'psychiatry', 'oncology', 'std']) else 'internal'
    
    # 3. יצירת תגית ניתוב (Routing tag) מבוססת על ציון הביטחון של מודל ה-AI
    if data.confidence_score < 0.6:
        routing_tag = 'escalate-to-doctor'
    elif data.confidence_score < 0.8:
        routing_tag = 'needs-review'
    else:
        routing_tag = 'auto-approved'

    # 4. החזרת האובייקט המועשר (כולל מזהה ייחודי וחותמת זמן כנדרש)
    return {
        'document_id': str(uuid.uuid4()),
        'department': department,
        'sensitivity': sensitivity,
        'routing_tag': routing_tag,
        'processed_at': datetime.datetime.utcnow().isoformat()
    }

@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    """Universal document extractor for multipart/form-data uploads (e.g. from n8n).
    Routes by filename extension and always returns {"text": ..., "images": [...]}
    (or {"error": ...} on failure)."""
    try:
        content = await file.read()
        lower_name = (file.filename or "").lower()

        if lower_name.endswith(".docx"):
            return _extract_docx(content)
        else:
            # Default to PDF for .pdf or unknown extensions.
            return _extract_pdf(content)

    except Exception as e:
        return {"error": str(e)}


def _extract_pdf(content: bytes):
    """Extract text + up to MAX_IMAGES Base64 images from PDF bytes."""
    doc = fitz.open(stream=content, filetype="pdf")

    text = ""
    images = []

    for page in doc:
        text += page.get_text()

        if len(images) < MAX_IMAGES:
            for img in page.get_images(full=True):
                if len(images) >= MAX_IMAGES:
                    break
                xref = img[0]
                base_image = doc.extract_image(xref)
                images.append({
                    "mime_type": f"image/{base_image['ext']}",
                    "data": base64.b64encode(base_image["image"]).decode("utf-8"),
                })

    doc.close()
    return {"text": text.strip(), "images": images}


def _extract_docx(content: bytes):
    """Extract all paragraph text from DOCX bytes (no image extraction)."""
    document = docx.Document(io.BytesIO(content))
    text = "\n".join(p.text for p in document.paragraphs)
    return {"text": text.strip(), "images": []}


@app.post("/vectorize")
def vectorize(data: VectorizeRequest):
    """Embeds the given text with Google's embedding model and upserts it into Pinecone
    for semantic search. The original text is stored in the vector metadata for retrieval."""
    # Reference the module-level clients initialized at startup.
    global pinecone_index, ai_client

    # Verify required services are initialized.
    if pinecone_index is None or ai_client is None:
        raise HTTPException(
            status_code=500,
            detail="Vectorization services not initialized (Pinecone and/or Gemini).",
        )

    try:
        # Generate a 768-dimension embedding from the text (google-genai SDK).
        # NOTE: text-embedding-004 is not available on this API; gemini-embedding-001
        # is the current model. We request output_dimensionality=768 to match the
        # Pinecone index (dimension=768, metric=cosine).
        response = ai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=data.text,
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
        embedding_vector = response.embeddings[0].values

        # Merge the original text into the metadata so it can be read back on search.
        pinecone_index.upsert(vectors=[
            (data.document_id, embedding_vector, {**data.metadata, "text": data.text})
        ])

        return {
            "status": "success",
            "document_id": data.document_id,
            "message": "Document embedded and upserted into Pinecone.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vectorization failed: {e}")


@app.post("/search")
def search(data: SearchRequest):
    """Semantic search: embeds the query and returns the top-k most similar documents
    from Pinecone, along with their stored medical metadata."""
    global ai_client, pinecone_index

    # Verify required services are initialized.
    if pinecone_index is None or ai_client is None:
        raise HTTPException(
            status_code=500,
            detail="Search services not initialized (Pinecone and/or Gemini).",
        )

    try:
        # Embed the query with the same model/dimension used at indexing time
        # (gemini-embedding-001 @ 768 dims) so it matches the Pinecone index.
        response = ai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=data.query,
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
        query_vector = response.embeddings[0].values

        # Query Pinecone for the nearest neighbours.
        search_results = pinecone_index.query(
            vector=query_vector,
            top_k=data.top_k,
            include_metadata=True,
        )

        # Parse matches into a clean, structured list.
        parsed_list = []
        for match in search_results.matches:
            metadata = match.metadata or {}
            parsed_list.append({
                "document_id": match.id,
                "score": match.score,
                "text": metadata.get("text", ""),
                "department": metadata.get("department", ""),
                "sensitivity": metadata.get("sensitivity", ""),
                "routing_tag": metadata.get("routing_tag", ""),
            })

        return {"results": parsed_list}

    except Exception as e:
        print(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")