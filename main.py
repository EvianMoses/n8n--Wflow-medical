from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import uuid, datetime, base64, io
import fitz  # PyMuPDF
import docx  # python-docx
app = FastAPI()

# Maximum number of images to extract from an uploaded PDF.
MAX_IMAGES = 3

# המבנה שאנחנו מצפים לקבל מ-n8n (אחרי ש-Gemini ניתח את המסמך)
class GeminiResult(BaseModel):
    classification: str
    sentiment: str
    confidence_score: float
    entities: dict

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