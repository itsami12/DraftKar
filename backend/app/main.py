import asyncio, base64, logging
from typing import Optional
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from app.config.settings import settings
from app.documents.registry import DEFS, DOCS, form_spec
from app.documents.templates import build
from app.pdf.builder import render_pdf
from app.schemas.documents import INPUT_MODELS, Content, GenerateRequest, LoginRequest, Placement
from app.services import cnic as cnic_svc, cnic_vision, ocr
from app.services.auth import check_credentials, issue_token, require_user
from app.services.image import BAD_UPLOAD_MESSAGE, BadUpload, prepare_for_ocr, prepare_for_pdf, read_upload
from app.services.llm import LLMUnavailable, generate_clauses

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="DraftKar API")
app.add_middleware(CORSMiddleware, allow_origins=settings.ALLOWED_ORIGINS, allow_origin_regex=r"https://.*\.vercel\.app",
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])

@app.exception_handler(RequestValidationError)
async def _validation(_, __):
    return JSONResponse({"detail": "Please check the information and try again."}, status_code=422)


OCR_FALLBACK_MESSAGE = "We couldn't analyze the stamp paper. You can continue with manual positioning."
GEN_ERROR = "We couldn't generate the document right now. Please try again."


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login")
def login(body: LoginRequest):
    if not settings.JWT_SECRET or not check_credentials(body.username, body.password):
        raise HTTPException(401, "Invalid username or password.")
    return {"token": issue_token(body.username)}


@app.get("/documents")
def list_documents(_: str = Depends(require_user)):
    return [{"type": k, **v} for k, v in DOCS.items()]


def _check(t):
    if t not in DEFS:
        raise HTTPException(404, "Unknown document type.")


@app.get("/documents/{document_type}")
def get_document(document_type: str, _: str = Depends(require_user)):
    _check(document_type)
    return {**DOCS[document_type], **form_spec(document_type)}


@app.post("/documents/{document_type}/generate")
async def generate(document_type: str, body: GenerateRequest, fmt: str = Query("pdf", alias="as"), _: str = Depends(require_user)):
    """Default: returns the standard PDF. With ?as=json: {content, pdf_base64} so the client can reuse `content` for stamp paper (no second LLM call)."""
    _check(document_type)
    try:
        answers = INPUT_MODELS[document_type].model_validate(
            {k: (str(v).strip() if v is not None else "") for k, v in body.answers.items()}).model_dump()
    except ValidationError:
        raise HTTPException(422, "Please complete all required fields.")
    for k, v in list(answers.items()):  # canonical LTR form XXXXX-XXXXXXX-X regardless of document language
        if k.endswith("_cnic") and v:
            answers[k] = cnic_svc.normalize_cnic(v) or v
    extras = []
    if document_type == "rent_agreement":
        extras = [l.strip() for l in answers.get("additional_clauses", "").splitlines() if l.strip()][:15]
        answers["additional_clauses"] = extras
    try:
        out = await generate_clauses(document_type, body.language, answers, extras)
        out.clauses = [cnic_svc.fix_reversed_cnics_in_text(t) for t in out.clauses]
        out.additional_clauses = [cnic_svc.fix_reversed_cnics_in_text(t) for t in out.additional_clauses]
        content = build(document_type, body.language, answers, out)
        pdf = render_pdf(content)
    except LLMUnavailable:
        raise HTTPException(502, GEN_ERROR)
    except Exception:
        logging.exception("generation failed")
        raise HTTPException(500, GEN_ERROR)
    if fmt == "json":
        return JSONResponse({"content": content, "pdf_base64": base64.b64encode(pdf).decode()})
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{document_type}_{body.language}.pdf"'})


@app.post("/cnic/extract")
async def cnic_extract(front: Optional[UploadFile] = File(None), back: Optional[UploadFile] = File(None), language: str = Form("english"),
                       _: str = Depends(require_user)):
    """CNIC FRONT + BACK -> ONE multimodal Groq vision request (image 1 = front, image 2 = back) -> Pydantic -> deterministic
    CNIC normalization -> ONE reviewable profile of ONE person. Browser -> FastAPI -> Groq; the key never leaves the server.
    Images live in memory for this request only and are never stored; extracted values are never logged. A failed read returns
    ok=false with empty fields (manual entry always works). OCR.Space is not involved (it is used for stamp paper only)."""
    if front is None:
        raise HTTPException(400, cnic_vision.MSG_NEED_FRONT)
    if back is None:
        raise HTTPException(400, cnic_vision.MSG_NEED_BACK)
    try:
        f_img, b_img = await read_upload(front), await read_upload(back)
    except BadUpload:
        raise HTTPException(400, BAD_UPLOAD_MESSAGE)
    return await cnic_vision.extract_cnic(f_img, b_img)  # `language` is accepted for compatibility; extracted text is never translated


@app.post("/documents/{document_type}/render")
def render_standard(document_type: str, content: Content, _: str = Depends(require_user)):
    """Renders the user-approved (possibly edited) document as the standard A4 PDF. No LLM involved."""
    _check(document_type)
    try:
        pdf = render_pdf(content.model_dump())
    except Exception:
        logging.exception("render failed")
        raise HTTPException(500, "We couldn't create the PDF. Please try again.")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{document_type}.pdf"'})


@app.post("/documents/{document_type}/stamp-paper/analyze")
async def stamp_analyze(document_type: str, file: UploadFile = File(...), _: str = Depends(require_user)):
    """Validates the image, runs OCR.Space server-side, returns normalized OCR info + a suggested placement.
    OCR failure is NOT an error: the response has ok=false and a default placement so the user can position manually."""
    _check(document_type)
    try:
        img = await read_upload(file)
    except BadUpload:
        raise HTTPException(400, BAD_UPLOAD_MESSAGE)
    w, h = img.size
    try:
        jpeg, sw, sh = prepare_for_ocr(img)
        data = await ocr.analyze(jpeg, sw, sh)
        return {"ok": True, "message": "", **data}
    except Exception as e:
        if not isinstance(e, ocr.OCRError):
            logging.exception("stamp analysis failed")
        return {"ok": False, "message": OCR_FALLBACK_MESSAGE, "text": "", "regions": [], "image": {"width": w, "height": h},
                "suggested": ocr.suggest_placement([], h)}


@app.post("/documents/{document_type}/stamp-paper/render")
async def stamp_render(document_type: str, file: UploadFile = File(...), content: str = Form(...), placement: str = Form(...),
                       _: str = Depends(require_user)):
    _check(document_type)
    try:
        c, p = Content.model_validate_json(content), Placement.model_validate_json(placement)
    except ValidationError:
        raise HTTPException(422, "Please check the document and its position, then try again.")
    try:
        img = await read_upload(file)
    except BadUpload:
        raise HTTPException(400, BAD_UPLOAD_MESSAGE)
    try:
        pdf = render_pdf(c.model_dump(), bg=prepare_for_pdf(img), placement=p.model_dump())
    except Exception:
        logging.exception("stamp render failed")
        raise HTTPException(500, "We couldn't create the stamp paper PDF. Please try again.")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{document_type}_stamp_paper.pdf"'})
