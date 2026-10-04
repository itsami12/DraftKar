import json, logging
import httpx
from pydantic import ValidationError
from app.config.settings import settings
from app.schemas.documents import LLMOutput

log = logging.getLogger("draftkar.llm")
URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMUnavailable(Exception):
    pass


SYSTEM = (
    "You are a drafting assistant for Pakistani stamp-paper document writers. "
    "Write the numbered operative clauses of the requested document, in formal legal wording, in the requested language "
    "(English, or Urdu in proper Urdu script - never Roman Urdu). "
    "Rules: use ONLY facts given by the user; never invent names, numbers, CNICs, amounts, dates or addresses; "
    "copy names, CNICs and numbers exactly as given; do not include a title, party descriptions, signature blocks, "
    "numbering characters, markdown or layout instructions. "
    'Respond with ONLY a JSON object: {"clauses": ["clause text", ...], "additional_clauses": [...]} where "clauses" has 5 to 10 clauses. '
    "User-provided additional clauses are explicit instructions for the document. Preserve their meaning and include them in the generated document. "
    "You may correct grammar or format the wording professionally, but do not materially alter the user's intended condition, "
    "invent unrelated obligations, or silently remove the clause. "
    '"additional_clauses" must contain exactly one professionally worded clause per user-provided additional clause, in the same order '
    "(an empty list if the user provided none); do not repeat them inside \"clauses\"."
)


async def generate_clauses(doc_type: str, language: str, answers: dict, extras: list | None = None) -> LLMOutput:
    extras = extras or []
    if settings.MOCK_LLM:
        return LLMOutput(additional_clauses=extras, clauses=[f"Sample clause {i} (mock mode)." if language == "english" else f"نمونہ شق نمبر {i}۔" for i in range(1, 5)])
    if not settings.GROQ_API_KEY:
        raise LLMUnavailable("GROQ_API_KEY missing")
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Document type: {doc_type}\nLanguage: {language}\nUser information (JSON):\n"
                                    + json.dumps({k: v for k, v in answers.items() if v}, ensure_ascii=False)},
    ]
    last = None
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(3):
            try:
                r = await client.post(URL, headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, json={
                    "model": settings.GROQ_MODEL, "messages": msgs, "temperature": 0.2, "max_completion_tokens": 6000,
                    "response_format": {"type": "json_object"}})
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
            except Exception as e:  # network / auth / rate limit
                log.warning("Groq call failed (attempt %s): %s", attempt + 1, type(e).__name__)
                if attempt == 2:
                    raise LLMUnavailable() from e
                continue
            try:
                out = LLMOutput.model_validate(json.loads(content))
                if len(out.additional_clauses) == len(extras):
                    return out
                last = out
                raise ValueError("additional_clauses count mismatch")
            except (json.JSONDecodeError, ValidationError, ValueError):
                log.warning("Invalid LLM JSON (attempt %s)", attempt + 1)
                msgs += [{"role": "assistant", "content": content},
                         {"role": "user", "content": f'Invalid. Return ONLY JSON {{"clauses": [5-10 strings], "additional_clauses": [exactly {len(extras)} strings, one per user clause, same order]}}.'}]
    if last is not None and extras:  # never drop a user clause: fall back to their own wording
        last.additional_clauses = list(extras)
        return last
    raise LLMUnavailable("invalid JSON after retries")
