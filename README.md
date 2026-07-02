# Chess Openings

A small FastAPI + React explorer for local Lichess opening taxonomy data.

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python download_openings.py
uvicorn main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173.

## Deployment notes

The frontend is a normal Vite app and deploys cleanly to Vercel from the
`frontend/` directory:

```bash
npm install
npm run build
```

Set `VITE_API_URL` in Vercel to the deployed backend URL. The local default is
`http://localhost:8000`, which only works on your machine.

The FastAPI backend can be hosted separately on a Python host such as Render,
Railway, Fly.io, or a Vercel Python Function. If you deploy it serverlessly, set
`OPENINGS_WRITE_CACHE=0` so runtime cache files are kept in memory instead of
being written to the deployment filesystem.

Set `FRONTEND_ORIGINS` on the backend to the deployed frontend URL, for example:

```text
FRONTEND_ORIGINS=https://your-app.vercel.app
```

## Data flow

The backend loads `backend/openings/*.tsv` once. Each `/position` request checks
`backend/data/prefix_cache.json` for the current move prefix first. If the prefix
is not cached, it scans the local TSV data for named continuations, returns those
rows, and writes the result back to the cache.

The included opening TSV files come from
https://github.com/lichess-org/chess-openings, which publishes the data as CC0.
