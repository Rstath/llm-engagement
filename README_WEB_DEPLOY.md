# Free web version: GitHub Pages + FastAPI backend

This version removes Streamlit from the participant UI.

## Architecture

- `frontend/`: static HTML/CSS/JS. Deploy this folder with GitHub Pages.
- `backend/`: FastAPI server. Deploy this on Render free web service or run locally.
- LLM calls stay inside the backend, so participants cannot see prompts, models, researcher routes, or database logic.

GitHub Pages cannot run Python or LLMs. It only hosts static HTML/CSS/JS, so the backend is required.

## Local run

Open two terminals.

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Start LM Studio local server at `http://localhost:1234/v1/chat/completions`, or edit `backend/.env`.

### 2. Frontend

Open `frontend/config.js` and keep:

```js
window.API_BASE_URL = "http://127.0.0.1:8000";
```

Then serve the frontend folder, for example:

```bash
cd frontend
python -m http.server 5500
```

Open:

```text
http://127.0.0.1:5500
```

Researcher page:

```text
http://127.0.0.1:5500/#researcher
```

The researcher password is `RESEARCHER_PASSWORD` from `backend/.env`.

## Free deployment suggestion

### Frontend: GitHub Pages

Push the `frontend/` files to your GitHub Pages repository. In `frontend/config.js`, replace the API URL with your deployed backend URL.

Example:

```js
window.API_BASE_URL = "https://your-render-service.onrender.com";
```

### Backend: Render free web service

Use the included `backend/render.yaml` or create a new Render Web Service manually:

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Set these environment variables in Render:

```text
APP_SECRET=<long random value>
RESEARCHER_PASSWORD=<your researcher password>
ALLOWED_ORIGINS=https://YOUR_USERNAME.github.io
LOCAL_LLM_BASE_URL=<your OpenAI-compatible LLM endpoint>
LOCAL_LLM_API_KEY=<key if needed>
SMALL_LLM_MODEL=<small model name>
MEDIUM_LLM_MODEL=<medium model name>
```

## Important limitation for fully free LLMs

Render free does not give you a GPU. It can host the FastAPI backend, but not a large local model. For the LLM endpoint you have three realistic choices:

1. **Local pilot only:** run LM Studio on your computer and use the local frontend/backend for testing.
2. **Free/low-power online pilot:** use a very small model on Hugging Face Spaces CPU and expose an OpenAI-compatible endpoint.
3. **Real online participant study with better models:** use a paid GPU endpoint later, such as RunPod or Hugging Face GPU.

## Security changes from Streamlit version

- Researcher data is never embedded in the frontend.
- The researcher dashboard calls `/api/researcher/*`.
- The backend requires a password-derived token for researcher endpoints.
- Participants only receive their own `participant_id`.
- Query strings are not used for access control.

This is enough to prevent casual URL changes from opening researcher data. For formal production security, add proper user accounts, HTTPS-only deployment, stronger session cookies, and managed database backups.
