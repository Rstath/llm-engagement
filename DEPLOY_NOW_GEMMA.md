# Deploy the simplified web app with hosted Gemma models

This version is intentionally simple:

- `frontend/` is plain HTML/CSS/JavaScript hosted on GitHub Pages.
- `backend/` is one FastAPI app hosted on Render.
- The backend calls OpenRouter's OpenAI-compatible API.
- The LLM API key is stored only on Render, never in the frontend.

## Model conditions

Use these first:

```env
SMALL_LLM_MODEL=google/gemma-3n-e4b-it
MEDIUM_LLM_MODEL=google/gemma-4-31b-it:free
```

OpenRouter currently lists `google/gemma-4-31b-it:free`. For the small condition, `google/gemma-3n-e4b-it` is the available E4B-class Gemma model. If your provider later exposes exact Gemma 4 E4B, change only `SMALL_LLM_MODEL` in Render.

---

## 1. Push this folder to GitHub

From the project root:

```powershell
git init
git add .
git commit -m "Initial simplified Gemma web app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

If Git says `backend/ does not have a commit checked out`, run:

```powershell
Remove-Item -Recurse -Force backend\.git
Remove-Item -Recurse -Force frontend\.git
```

Then repeat `git add .`.

---

## 2. Create an OpenRouter API key

Create an OpenRouter account and API key.

You do not put this key in GitHub. You add it only to Render environment variables.

---

## 3. Deploy the backend on Render

Render → New → Web Service → connect your GitHub repo.

Use:

```text
Root Directory: backend
Runtime: Python
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Add these Render environment variables:

```env
APP_SECRET=make-a-long-random-secret
RESEARCHER_PASSWORD=choose-a-password
DB_PATH=human_experiment_data.db
ALLOWED_ORIGINS=https://YOUR_GITHUB_USERNAME.github.io
LLM_BASE_URL=https://openrouter.ai/api/v1/chat/completions
LLM_API_KEY=your_openrouter_api_key
OPENROUTER_SITE_URL=https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/
OPENROUTER_APP_NAME=LLM Engagement Study
SMALL_LLM_MODEL=google/gemma-3n-e4b-it
MEDIUM_LLM_MODEL=google/gemma-4-31b-it:free
DEFAULT_TEMPERATURE=0.7
DEFAULT_MAX_AGENT_TOKENS=130
TARGET_TOTAL_TURNS=14
```

Deploy and copy your Render URL, for example:

```text
https://your-backend-name.onrender.com
```

Test this in the browser:

```text
https://your-backend-name.onrender.com/api/meta
```

You should see JSON.

---

## 4. Connect the frontend to Render

Edit:

```text
frontend/config.js
```

Change:

```js
window.API_BASE_URL = "https://YOUR_RENDER_SERVICE.onrender.com";
```

Commit and push:

```powershell
git add frontend/config.js
git commit -m "Connect frontend to backend"
git push
```

---

## 5. Enable GitHub Pages

GitHub repo → Settings → Pages.

Set:

```text
Source: GitHub Actions
```

Then go to:

```text
Actions → Deploy frontend to GitHub Pages
```

Wait until it is green.

Your app will be available at:

```text
https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/
```

---

## 6. Update CORS after GitHub Pages is live

Go back to Render → Environment.

Change:

```env
ALLOWED_ORIGINS=https://YOUR_GITHUB_USERNAME.github.io
```

Save/redeploy.

---

## 7. Test the app

Participant flow:

```text
consent → pre-questionnaire → BFI → topic selection → chat → thank you
```

Researcher route:

```text
https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/#researcher
```

Use the `RESEARCHER_PASSWORD` you set in Render.

---

## Important limitations

This is the simplest deployable version, but Render free storage is not reliable for long-term SQLite persistence. For the thesis pilot it is okay. For real data collection, export your CSV often from the researcher page or upgrade to PostgreSQL later.

Free OpenRouter models can have rate limits or temporary unavailability. If a model stops responding, change only the model ID in Render.
