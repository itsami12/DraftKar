# DraftKar — Testing guide

Start backend (`uvicorn app.main:app --reload --port 8000`) and frontend (`npm run dev`) first (see README).

1. **Login** — open http://localhost:3000. Wrong credentials → "Invalid username or password." Correct `DEMO_USERNAME` / `DEMO_PASSWORD` → document dashboard.
2. **CNIC extraction path** — upload the front and back sides together → review the extracted identity and address fields → edit if needed → Apply Information.
   Check: front/back are both required for a complete identity metadata extraction; names and addresses stay in the original language; the CNIC is normalized to the canonical `XXXXX-XXXXXXX-X` format.
3. **Each document** (Rent Agreement, Affidavit, Undertaking, Authority Letter) × **English and Urdu**:
   select document → select language → fill every section (witnesses optional) → Generate document → PDF preview appears → Download PDF → open the file in another viewer.
   Urdu check: connected letters, right-to-left lines, names/CNICs/numbers intact.
4. **Errors**
   - Leave a required field empty and press Continue → "Please complete all required fields."
   - Groq unavailable (set a wrong `GROQ_API_KEY`, restart backend) → "We couldn't generate the document right now. Please try again." (no stack trace shown)
   - Invalid LLM JSON → backend retries up to 3 times with a correction prompt, then shows the same friendly error.
4. **Responsive** — check desktop, tablet (~768px) and mobile (~390px) widths.
5. **Offline layout test (no Groq)** — start backend with `MOCK_LLM=1` to test PDF layout with placeholder clauses. Never use in production.
6. **Stamp-paper OCR check** — upload a stamp-paper image to the document flow and verify OCR.Space continues to handle the stamp paper only. CNIC extraction should not route through OCR.Space in the live Groq configuration.
7. **Deployed** — repeat tests 1–6 on the Vercel URL (Rent Agreement + Urdu is the required smoke test).
