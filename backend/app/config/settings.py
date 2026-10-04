import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "")  # STAMP PAPER analysis only; CNIC no longer uses OCR.Space
    # CNIC extraction: Groq vision model reading BOTH card sides in one request. Uses its OWN key (separate from document generation);
    # falls back to GROQ_API_KEY when GROQ_VISION_API_KEY is not set. Keys stay on the backend.
    GROQ_VISION_API_KEY = os.getenv("GROQ_VISION_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
    # Reasoning tokens count against max_completion_tokens: with thinking on, Urdu reading can use the whole budget and return no JSON.
    # "none" turns thinking off. If the model rejects it (HTTP 400) the request is retried without these params automatically.
    GROQ_VISION_REASONING_EFFORT = os.getenv("GROQ_VISION_REASONING_EFFORT", "none")  # empty = not sent
    GROQ_VISION_REASONING_FORMAT = os.getenv("GROQ_VISION_REASONING_FORMAT", "")      # optional: hidden | parsed | raw; empty = not sent
    # Qwen vision can return a truncated generation under Groq's strict schema validator. JSON mode keeps the
    # one-request flow while allowing the local Pydantic validation to handle the response consistently.
    GROQ_VISION_STRUCTURED = os.getenv("GROQ_VISION_STRUCTURED", "0") != "0"           # 1 = strict json_schema mode
    GROQ_VISION_ADDRESS_CROP = os.getenv("GROQ_VISION_ADDRESS_CROP", "1") != "0"       # zoomed crop of the back attached as image 3 of the same request
    GROQ_VISION_TIMEOUT = float(os.getenv("GROQ_VISION_TIMEOUT", "60"))
    DEMO_USERNAME = os.getenv("DEMO_USERNAME", "")
    DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    # Dev/test only: skips Groq and returns generic clauses so PDF layout can be tested offline.
    MOCK_LLM = os.getenv("MOCK_LLM", "0") == "1"


settings = Settings()
