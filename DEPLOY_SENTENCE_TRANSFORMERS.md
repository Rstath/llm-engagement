# Sentence-Transformers deployment update

This build keeps the existing SQLite persistence path unchanged:

- `DB_PATH=/var/data/human_experiment_data.db`
- Render disk mount: `/var/data`

## Changes

1. Added `sentence-transformers>=3.0,<4.0` to `backend/requirements.txt`.
2. Updated the researcher Latin-square dashboard target to 16 participants / 2 per sequence.
3. No database schema, deletion, reset, or migration logic was added.
4. Existing completed conversations are recomputed when `/api/researcher/metrics` is loaded.

## Deploy safely

Redeploy the EXISTING Render service. Do not create a new service, delete/recreate the persistent disk, or change `DB_PATH`.

After deployment, open the researcher metrics dashboard and verify:

- existing participants/conversations are still present;
- `Embedding model` shows `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, not the hash fallback;
- metrics are recalculated for completed conversations.

## Resource note

Sentence-Transformers also installs PyTorch and loads a neural embedding model. A 512 MB Render instance may be too memory-constrained for reliable loading/recalculation of all metrics. If the service is killed/restarts due to memory, increase the Render instance RAM rather than reverting to hash metrics.
