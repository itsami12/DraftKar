from typing import List, Literal
from pydantic import BaseModel, Field, create_model, field_validator, model_validator
from app.documents.registry import DEFS

Language = Literal["english", "urdu"]


class LLMOutput(BaseModel):
    """What the LLM is allowed to return: wording only, never layout."""
    clauses: List[str] = Field(min_length=3, max_length=15)
    additional_clauses: List[str] = Field(default_factory=list, max_length=15)

    @field_validator("clauses", "additional_clauses")
    @classmethod
    def non_empty(cls, v):
        return [c.strip() for c in v if isinstance(c, str) and c.strip()]


def _build(doc_type):
    fields = {}
    for f in DEFS[doc_type]["fields"]:
        key, required = f[0], f[4]
        fields[key] = (str, Field(min_length=1, max_length=2000)) if required else (str, Field(default="", max_length=2000))
    return create_model(f"{doc_type}_input", **fields)


# One validated input schema per document type (built from the registry).
INPUT_MODELS = {t: _build(t) for t in DEFS}


class GenerateRequest(BaseModel):
    language: Language
    answers: dict


class LoginRequest(BaseModel):
    username: str
    password: str


class Content(BaseModel):
    """Fully rendered, deterministic document content (output of the template engine). Sent back by the client for stamp-paper rendering."""
    title: str = Field(min_length=1, max_length=200)
    meta: List[str] = Field(default_factory=list, max_length=10)
    intro: List[str] = Field(max_length=10)
    clauses: List[str] = Field(max_length=40)
    extra_title: str = ""
    extra_clauses: List[str] = Field(default_factory=list, max_length=20)
    closing: str = Field(max_length=2000)
    signers: List[List[str]] = Field(max_length=4)
    witnesses: List[List[str]] = Field(default_factory=list, max_length=4)
    labels: dict
    rtl: bool

    @field_validator("title", "closing", "extra_title")
    @classmethod
    def strip(cls, v, info):
        v = v.strip()
        if info.field_name == "title" and not v:
            raise ValueError("title required")
        return v

    @model_validator(mode="after")
    def extra_heading(self):
        # extra clauses always get a heading; no clauses -> no heading (never an empty section)
        if self.extra_clauses and not self.extra_title:
            self.extra_title = "اضافی شرائط / شقیں" if self.rtl else "Additional Terms / Clauses"
        if not self.extra_clauses:
            self.extra_title = ""
        return self

    @field_validator("meta", "intro", "clauses", "extra_clauses")
    @classmethod
    def clean_list(cls, v):
        if any(len(x) > 3000 for x in v):
            raise ValueError("too long")
        return [x.strip() for x in v if x.strip()]  # blank blocks are dropped

    @field_validator("signers")
    @classmethod
    def signers_ok(cls, v):
        if not v or any(len(s) != 3 or not s[1].strip() for s in v):
            raise ValueError("each signer needs role, name and CNIC")
        return [[x.strip() for x in s] for s in v]

    @field_validator("witnesses")
    @classmethod
    def wit_ok(cls, v):
        if any(len(w) != 2 for w in v):
            raise ValueError("witness needs name and CNIC")
        return [[x.strip() for x in w] for w in v if w[0].strip()]


class Placement(BaseModel):
    x: float = Field(ge=0, le=0.9)
    y: float = Field(ge=0, le=0.95)
    width: float = Field(ge=0.1, le=1)
    font_scale: float = Field(default=1.0, ge=0.5, le=2.0)
