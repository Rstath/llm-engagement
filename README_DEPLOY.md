# Deployment README — LLM Engagement Study

## Structure
- `frontend/`: GitHub Pages static interface (`index.html`, `app.js`, `styles.css`, `config.js`, assets).
- `backend/`: FastAPI application, Render deployment settings, Python requirements and environment example.
- `.github/workflows/`: frontend deployment automation.
- `README_TESTS.md`: separate offline research-analysis instructions.

## Production setup
The current study uses a FastAPI backend on Render and an OpenAI-compatible supervisor-hosted LLM endpoint. The two experimental models are Gemma 3 4B and Gemma 3 27B quantized variants. The frontend never holds an API secret.

1. Keep your **existing Render service and persistent disk**; do not recreate the disk or reset the database.
2. In Render, use root directory `backend`, build command `pip install -r requirements.txt`, start command `uvicorn main:app --host 0.0.0.0 --port $PORT`.
3. Set the environment variables described in `backend/.env.example`, including `APP_SECRET`, `RESEARCHER_PASSWORD`, `ALLOWED_ORIGINS`, the OpenAI-compatible LLM URL and model identifiers.
4. Preserve `DB_PATH=/var/data/human_experiment_data.db` and the disk mount `/var/data` to retain participant progress, questionnaires and access codes.
5. Confirm the supervisor endpoint is reachable from Render and both configured models respond to `/api/llm-diagnostic` before collecting new data.
6. Publish the frontend using the existing GitHub Pages workflow and set `frontend/config.js` to your backend URL.

**Security:** Never commit `.env`, API keys, researcher passwords or participant databases. The included CSV exports are research data; store and share them only under your study's data-protection procedures. If the repository is public, exclude these CSVs before pushing.

## Local development (Windows PowerShell)
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Configure backend/.env, then:
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
In another terminal, serve `frontend/` with `python -m http.server 5500`. For local testing set `frontend/config.js` to `http://127.0.0.1:8000`.

## Before redeployment
- Back up the Render SQLite database and exported study CSVs.
- Verify CORS origin, database path, and both model IDs.
- Do not rely on the lightweight server-side preliminary metrics for final thesis inference; see `README_TESTS.md`.
