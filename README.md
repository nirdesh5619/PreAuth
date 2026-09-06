# Folio — prior authorization agents

Local multi-agent console. A coordinator fans out to Document, Clinical, and Policy, a Matcher scores payer criteria, a human reviews gaps, and an Assembler drafts a letter of medical necessity. Nothing is submitted to a payer.

## Run locally

Two terminals.

Secrets live in a gitignored `.env` at the repo root.

```bash
cp .env.example .env   # then set OPENAI_API_KEY
cd backend
uv sync --extra dev
uv run uvicorn pauth.main:app --reload --port 8000
```

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). With `OPENAI_API_KEY` set, Document / Clinical / Policy / Matcher / Assembler call OpenAI. Without a key the graph still runs on deterministic stubs.

`PAUTH_FORCE_STUBS=1` in `.env` keeps stubs even if a key is present. Restart the API after changing `.env`. `GET /api/health` reports `use_llm` without exposing the key.

## Tests

```bash
cd backend && uv run pytest
```

## Notes

- Case data lives in `backend/data/` (gitignored).
- Policy text is fixture markdown under `backend/pauth/policies/`.
- Dummy attachments (PDF): `backend/pauth/fixtures/attachments/`.
