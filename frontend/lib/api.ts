import type { CnicResult, Content, DocMeta, DocSpec, Lang, Placement, StampAnalysis } from "@/types";
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const getToken = () => (typeof window === "undefined" ? null : sessionStorage.getItem("dk_token"));
export const setToken = (t: string | null) => (t ? sessionStorage.setItem("dk_token", t) : sessionStorage.removeItem("dk_token"));

export class ApiError extends Error { constructor(m: string, public status: number) { super(m); } }

async function call(path: string, init: RequestInit = {}) {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { ...init, headers: { ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...init.headers } });
  } catch { throw new ApiError("Can't reach the server. Check your connection and try again.", 0); }
  if (!res.ok) {
    let msg = "Something went wrong. Please try again.";
    try { const j = await res.json(); if (typeof j.detail === "string") msg = j.detail; } catch {}
    throw new ApiError(msg, res.status);
  }
  return res;
}
export async function login(username: string, password: string) {
  const r = await call("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
  setToken((await r.json()).token);
}
export const listDocs = async (): Promise<DocMeta[]> => (await call("/documents")).json();
export const getDoc = async (t: string): Promise<DocSpec> => (await call(`/documents/${t}`)).json();
export async function generate(t: string, language: Lang, answers: Record<string, string>): Promise<{ content: Content; pdf: Blob }> {
  const j = await (await call(`/documents/${t}/generate?as=json`, { method: "POST", body: JSON.stringify({ language, answers }) })).json();
  const bytes = Uint8Array.from(atob(j.pdf_base64), (c) => c.charCodeAt(0));
  return { content: j.content, pdf: new Blob([bytes], { type: "application/pdf" }) };
}
export async function renderStandard(t: string, content: Content): Promise<Blob> {
  return (await call(`/documents/${t}/render`, { method: "POST", body: JSON.stringify(content) })).blob();
}
export async function extractCnic(front: File | null, back: File | null, ur = false): Promise<CnicResult> {
  const fd = new FormData(); if (front) fd.append("front", front); if (back) fd.append("back", back); fd.append("language", ur ? "urdu" : "english");  // Urdu document: name/gender come back in Urdu  // goes to FastAPI only; the Groq vision key stays on the server
  return (await call("/cnic/extract", { method: "POST", body: fd })).json();
}
export async function analyzeStamp(t: string, file: File): Promise<StampAnalysis> {
  const fd = new FormData(); fd.append("file", file);
  return (await call(`/documents/${t}/stamp-paper/analyze`, { method: "POST", body: fd })).json();
}
export async function renderStamp(t: string, file: File, content: Content, placement: Placement): Promise<Blob> {
  const fd = new FormData(); fd.append("file", file); fd.append("content", JSON.stringify(content)); fd.append("placement", JSON.stringify(placement));
  return (await call(`/documents/${t}/stamp-paper/render`, { method: "POST", body: fd })).blob();
}
