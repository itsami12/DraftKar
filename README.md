# DraftKar

AI-powered document preparation for Pakistani document writers. Choose a document, choose English or Urdu, answer structured questions, and get a formatted PDF.

## Architecture
`Next.js → FastAPI → Groq → Pydantic → Template engine → ReportLab → PDF`

The LLM only returns validated JSON (`{"clauses": [...]}`) — wording, never layout. Parties, dates, amounts and the user's own declaration text come straight from the form into deterministic templates. Fonts, margins, page breaks, signature areas and RTL shaping are controlled by code (`backend/app/pdf/builder.py`).

## Tech stack
- **Next.js + TypeScript + Tailwind + lucide-react** (Vercel) — UI. The question forms are rendered from the backend's document registry, so one source of truth defines the fields.
- **FastAPI + Pydantic + Uvicorn** (Railway) — API, validation (per-document input models built from the registry), JWT auth.
- **Groq** (`GROQ_MODEL` for document drafting, `GROQ_VISION_MODEL=qwen/qwen3.8-27b` for CNIC front/back vision extraction) — clause drafting and structured CNIC extraction, with controlled retries.
- **ReportLab + arabic-reshaper + python-bidi + Amiri font (OFL, bundled)** — PDF with correct Urdu joining and RTL.

## Local setup
```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
# create backend/.env (see .env.example)
uvicorn app.main:app --reload --port 8000     # http://localhost:8000/health
```
```bash
cd frontend
npm install
# create frontend/.env.local with NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                                   # http://localhost:3000
```

## Environment variables
| Variable | Where | Purpose |
|---|---|---|
| GROQ_API_KEY | backend | Groq access (never sent to browser) |
| GROQ_MODEL | backend | document-generation model override |
| GROQ_VISION_MODEL | backend | CNIC vision model, default `qwen/qwen3.8-27b` |
| GROQ_VISION_STRUCTURED | backend | `0` = tolerant JSON mode (default), `1` = strict schema mode |
| DEMO_USERNAME / DEMO_PASSWORD | backend | the single demo login |
| JWT_SECRET | backend | signs session tokens |
| ALLOWED_ORIGINS | backend | CORS origins (`*.vercel.app` is also allowed) |
| MOCK_LLM | backend | `1` = dev-only offline test mode |
| NEXT_PUBLIC_API_URL | frontend | backend base URL |

## Demo credentials
Set in backend environment variables only (`backend/.env` locally, Railway variables in production). Not in the frontend, not committed.

## Testing
See [TESTING.md](TESTING.md).

## Deployment
### Before pushing to GitHub
Never commit `backend/.env` or any API key. The repository includes [backend/.env.example](backend/.env.example) as a safe template. Rotate any keys that have ever been exposed outside your password manager, then create fresh Railway variables.

### Railway backend
Create a Railway project from the GitHub repository, set the service root directory to `backend`, and deploy. `backend/railway.toml` supplies the start command and `/health` health check. Set these variables in Railway:

`GROQ_API_KEY`, `GROQ_VISION_API_KEY`, `GROQ_MODEL`, `GROQ_VISION_MODEL`, `GROQ_VISION_STRUCTURED=0`, `OCR_SPACE_API_KEY`, `DEMO_USERNAME`, `DEMO_PASSWORD`, `JWT_SECRET`, and `ALLOWED_ORIGINS=https://YOUR-VERCEL-PROJECT.vercel.app`.

Verify `https://YOUR-RAILWAY-DOMAIN/health` returns `{"status":"ok"}` and copy the public Railway domain.

### Vercel frontend
Import the same GitHub repository into Vercel, set the project root directory to `frontend`, and set `NEXT_PUBLIC_API_URL=https://YOUR-RAILWAY-DOMAIN`. Use the default Next.js build and start settings, then deploy.

After deployment, open the Vercel URL, log in with the Railway `DEMO_USERNAME` and `DEMO_PASSWORD`, and test CNIC extraction plus one English and one Urdu document.

## CNIC extraction flow
- CNIC front and back are uploaded separately and sent together in one Groq multimodal request.
- The CNIC workflow uses `qwen/qwen3.8-27b` directly for structured identity and address extraction.
- OCR.Space remains reserved for stamp-paper analysis only and is not used for CNIC identity/address extraction in normal operation.
- Extracted values are validated with Pydantic and CNIC number normalization before user review.
- CNIC vision uses tolerant JSON mode by default because strict schema validation can cause this model to return a truncated `{` response; set `GROQ_VISION_STRUCTURED=1` only when the selected model reliably supports Groq JSON schema output.

## Known limitations
No database, no printer integration, no automatic stamp-paper placement, no user accounts or document history. Urdu uses a Naskh-style font (Amiri), not Nastaliq. Generated documents are drafts — review before signing; they are not guaranteed to be legally valid.
