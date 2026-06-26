# 🏥 MedAI: Clinical Command Center & Intelligent Document Pipeline

MedAI is an automated, cloud-connected pipeline designed to intelligently process, route, and analyze medical documents in real-time. Powered by **n8n**, **Google Gemini 2.5 Flash**, and a custom **FastAPI Python backend**, this system watches for incoming clinical files (PDFs, DOCX), extracts their content (including images), and uses multi-modal AI to analyze the data. 

The system automatically extracts entities, determines document sensitivity, logs data to a cloud database, alerts staff of confidential files, and provides a live analytical dashboard.

## ✨ Key Features

* **Multi-Modal AI Analysis:** Uses Gemini 2.5 Flash to process both text and embedded images from medical documents (e.g., lab results, discharge summaries).
* **Intelligent Auto-Routing:** Custom Python microservice automatically categorizes documents and routes them to the correct hospital department.
* **PHI Sensitivity Detection:** Identifies highly sensitive files (e.g., Oncology, Psychiatry) and flags them with a `CONFIDENTIAL` tag.
* **Real-Time Email Alerting:** Automatically dispatches high-priority emails for confidential files and standard summaries for routine documents.
* **Cloud Logging & Output:** Appends parsed metadata to a Google Sheet and saves standardized JSON and Markdown reports directly to Google Drive.
* **Daily Digest:** Scheduled automated workflow that sends a 24-hour summary report of all processed documents.
* **Live Dashboard:** HTML/JS real-time dashboard displaying operational metrics and department routing efficiency.

---

## 🏗️ System Architecture

1.  **Trigger:** An n8n node monitors a specific Google Drive folder (`incoming_docs`) for new files.
2.  **Extraction:** The file is downloaded and sent to a local FastAPI service that extracts text and up to 3 embedded images using `PyMuPDF` and `python-docx`.
3.  **AI Processing:** The extracted data is sent to the Google Gemini API to generate a structured JSON containing a summary, classification, sentiment, medical entities, and action items.
4.  **Metadata Enrichment:** The AI's JSON output is passed back to the FastAPI service to determine the routing department, sensitivity level, and confidence score.
5.  **Storage & Delivery:** 
    * Metadata is logged into a **Google Sheet**.
    * Human-readable Markdown and JSON files are generated and uploaded to an `output_docs` Drive folder.
    * **Gmail** nodes send conditional email alerts.
    * The original file is deleted from the input folder to free up space.

---

## 🚀 Installation & Setup Guide

Even if you are new to n8n or Python, follow these steps to get the system running on your local machine.

### Prerequisites
* **Python 3.10+** installed on your machine.
* **n8n** installed (either via npm or Docker). *Note: If using Docker, ensure your `host.docker.internal` routing is configured correctly.*
* A **Google Cloud Project** with Drive, Sheets, and Gmail APIs enabled (for OAuth2 credentials).
* A **Google Gemini API Key** from Google AI Studio.

### Step 1: Set up the Python Backend
The Python backend handles file parsing and metadata enrichment.

1. Clone this repository and navigate to the project folder:
   `git clone https://github.com/yourusername/MedAI-Pipeline.git`
   `cd MedAI-Pipeline`
2. Create a virtual environment and activate it:
   `python -m venv venv`
   *(On Windows: `venv\Scripts\activate` | On Mac/Linux: `source venv/bin/activate`)*
3. Install the required dependencies:
   `pip install fastapi uvicorn pymupdf python-docx pydantic python-multipart`
4. Run the FastAPI server:
   `uvicorn main:app --host 0.0.0.0 --port 8000`
   *(The server must be running for n8n to process documents)*

### Step 2: Set up Google Workspace
1. Create two folders in your Google Drive: `incoming_docs` and `output_docs`.
2. Create a new Google Sheet named `Medic_doc_log`.
3. In the first row of the Sheet, create the following exact headers:
   `Document ID` | `Department` | `Sensitivity` | `Routing Tag` | `Processed At` | `Summary`

### Step 3: Import and Configure n8n Workflow
1. Open your n8n instance and click **Add Workflow** -> **Import from File**.
2. Select the provided `madical_docs_workFlow.json` file.
3. **Configure Credentials:** You will need to click on the nodes with errors (usually Google and Gemini nodes) and add your credentials:
   * **Google Drive Node:** Connect your Google account via OAuth2.
   * **Google Sheets Node:** Connect your Google account via OAuth2 and select your `Medic_doc_log` spreadsheet.
   * **Gmail Node:** Connect your Gmail account via OAuth2. Update the "Send To" fields with your email address.
   * **Gemini HTTP Request Node:** Add your Gemini API key in the authentication section.
4. **Update Folder IDs:** In the Google Drive trigger and upload nodes, ensure you select the specific Drive folders you created in Step 2.
5. Click **Save** and toggle the workflow to **Active**.

### Step 4: Set up the Dashboard (Optional)
1. In your Google Sheet, go to **Extensions > Apps Script**.
2. Create a simple `doGet` function that returns your sheet data as JSON. Deploy it as a Web App.
3. Open `dashboard.html` in your code editor and replace the `API_URL` constant with your new Google Apps Script deployment URL.
4. Open `dashboard.html` in any web browser to view your live stats.

---

## 🛠️ Usage

1. Start your Python backend (`uvicorn main:app`).
2. Ensure your n8n workflow is active.
3. Drop a medical document (PDF or DOCX) into your `incoming_docs` Google Drive folder.
4. Wait a few seconds. The pipeline will automatically pick it up, analyze it, and log the results.
5. Check your Email inbox for the summary or alert.
6. Check your Google Sheet and Dashboard to see the newly appended data.