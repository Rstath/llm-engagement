# Supervisor LLM endpoint setup

The backend now uses the supervisor-hosted OpenAI-compatible endpoint instead of OpenRouter.

## Render environment variables

Set/confirm these values in Render:

- `LLM_BASE_URL=http://150.140.142.76:1234/v1`
- `LLM_REQUEST_TIMEOUT_SECONDS=300`
- `LLM_API_KEY=` (blank unless the supervisor later enables authentication)
- `SMALL_LLM_MODEL=lmstudio-community/gemma-3-4B-it-QAT-GGUF`
- `MEDIUM_LLM_MODEL=lmstudio-community/gemma-3-27B-it-qat-GGUF`

The experiment's small/medium model conditions have NOT been changed.

## Server requirement

The server at `150.140.142.76:1234` must expose both experiment model IDs through its OpenAI-compatible API, or configure exact aliases for those IDs. Check `GET /v1/models` on that server.

After deployment, open:

`https://llm-engagement.onrender.com/api/llm-diagnostic`

The diagnostic now checks the configured supervisor server and tests both experimental model IDs. It does not send participant data.

## Request path

Frontend -> Render FastAPI `/api/chat` -> `http://150.140.142.76:1234/v1/chat/completions`

Participant progress, SQLite storage, Big Five context, prompts, assignments, metrics, questionnaires, and frontend behavior are unchanged.
