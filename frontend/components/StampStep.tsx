"use client";
import { useEffect, useRef, useState } from "react";
import { FileImage, Loader2, RefreshCw, UploadCloud, CheckCircle2, AlertCircle } from "lucide-react";
import { analyzeStamp, renderStamp } from "@/lib/api";
import type { Content, Placement, Region } from "@/types";

const OK_TYPES = ["image/jpeg", "image/png", "image/webp"];
const BAD = "Please upload a JPG, JPEG, PNG, or WebP image under 10 MB.";
const DEFAULT: Placement = { x: 0.1, y: 0.22, width: 0.8, font_scale: 1 };

export default function StampStep({ docType, content, onDone, onSkip, onBack }: { docType: string; content: Content; onDone: (url: string) => void; onSkip: () => void; onBack: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [phase, setPhase] = useState<"idle" | "analyzing" | "ready">("idle");
  const [msg, setMsg] = useState(""); const [ocrOk, setOcrOk] = useState(true); const [err, setErr] = useState("");
  const [place, setPlace] = useState<Placement>(DEFAULT);
  const [regions, setRegions] = useState<Region[]>([]); const [dim, setDim] = useState({ width: 1, height: 1 });
  const [drag, setDrag] = useState(false); const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null); const stage = useRef<HTMLDivElement>(null);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  async function pick(f?: File | null) {
    if (!f) return;
    if (!OK_TYPES.includes(f.type) || f.size > 10 * 1024 * 1024) { setErr(BAD); return; }
    setErr(""); setMsg(""); setFile(f); setUrl(URL.createObjectURL(f)); setPhase("analyzing"); setRegions([]);
    try {
      const r = await analyzeStamp(docType, f);
      setPlace(r.suggested); setRegions(r.regions); setDim(r.image); setOcrOk(r.ok);
      setMsg(r.ok ? "Stamp paper analyzed" : r.message); setPhase("ready");
    } catch (e: any) {
      if (e.status === 400) { setErr(e.message); setFile(null); setUrl(""); setPhase("idle"); return; }
      setPlace(DEFAULT); setOcrOk(false); setMsg("We couldn't analyze the stamp paper. You can continue with manual positioning."); setPhase("ready");
    }
  }

  function startDrag(e: React.PointerEvent) {
    const el = stage.current!; const rect = el.getBoundingClientRect(); const s = { px: e.clientX, py: e.clientY, p: place };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => setPlace({ ...s.p, x: clamp(s.p.x + (ev.clientX - s.px) / rect.width, 0, 0.9), y: clamp(s.p.y + (ev.clientY - s.py) / rect.height, 0, 0.95) });
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }

  async function create() {
    if (!file) return; setBusy(true); setErr("");
    try { onDone(URL.createObjectURL(await renderStamp(docType, file, content, place))); }
    catch (e: any) { setErr(e.message || "We couldn't create the stamp paper PDF. Please try again."); } finally { setBusy(false); }
  }

  // text size in the overlay scales with the sheet width (cqw), mirroring the PDF's 11.5pt (14pt Urdu) on a page of width pageW points
  const pageW = dim.width >= dim.height ? 841.89 : (841.89 * dim.width) / dim.height;
  const fs = ((content.rtl ? 14 : 11.5) * place.font_scale / pageW) * 100;
  const all = [...content.clauses.map((c, i) => `${i + 1}. ${c}`), ...(content.extra_clauses?.length ? [content.extra_title || "", ...content.extra_clauses.map((c, i) => `${content.clauses.length + i + 1}. ${c}`)] : [])];

  return (
    <div>
      <h1 className="font-display text-3xl font-bold text-ink">Upload your stamp paper</h1>
      <p className="mt-1 max-w-2xl text-neutral-600">Upload a clear scan or photo of the stamp paper where you want the generated document to appear.</p>
      {err && <p role="alert" className="mt-4 flex max-w-2xl items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700"><AlertCircle size={16} />{err}</p>}

      {phase === "idle" && (
        <div role="button" tabIndex={0} onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
          className={`mt-6 flex max-w-2xl cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed px-6 py-14 text-center transition ${drag ? "border-ink bg-stampsoft" : "border-line bg-white hover:border-ink"}`}>
          <UploadCloud size={36} className="text-stamp" />
          <p className="mt-3 font-medium text-ink">Drag &amp; drop your stamp paper here</p>
          <span className="btn btn-primary mt-4">Choose file</span>
          <p className="mt-3 text-xs text-neutral-500">JPG, JPEG, PNG, WebP • Maximum 10 MB</p>
        </div>)}
      <input ref={input} type="file" hidden accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />

      {phase === "analyzing" && (<div role="status" className="mt-6 flex max-w-2xl items-center gap-3 rounded-2xl border border-line bg-white p-6"><Loader2 className="animate-spin text-ink" /><span className="font-medium text-ink">Analyzing your stamp paper…</span></div>)}

      {phase === "ready" && (
        <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_300px]">
          <div>
            <p className={`mb-3 flex items-center gap-2 text-sm ${ocrOk ? "text-green-700" : "text-amber-700"}`}>{ocrOk ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}{msg}</p>
            <div ref={stage} className="relative select-none overflow-hidden rounded-xl border border-line shadow-sm" style={{ containerType: "inline-size" }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={url} alt="Your stamp paper" className="block w-full" draggable={false} />
              {regions.map((r, i) => (<div key={i} className="pointer-events-none absolute border border-amber-500/60" style={{ left: `${(r.x / dim.width) * 100}%`, top: `${(r.y / dim.height) * 100}%`, width: `${(r.width / dim.width) * 100}%`, height: `${(r.height / dim.height) * 100}%` }} />))}
              <div onPointerDown={startDrag} dir={content.rtl ? "rtl" : "ltr"} title="Drag to move" aria-label="Generated text position (drag to move)"
                className="absolute cursor-move overflow-hidden border border-dashed border-ink bg-white/40 text-black" style={{ left: `${place.x * 100}%`, top: `${place.y * 100}%`, width: `${place.width * 100}%`, height: `${Math.max(0.05, 0.93 - place.y) * 100}%`, fontSize: `${fs}cqw`, lineHeight: 1.5, touchAction: "none" }}>
                <div className="pointer-events-none"><div className="text-center font-bold" style={{ fontSize: "1.5em" }}>{content.title}</div>
                  {content.intro.map((t, i) => <p key={i} className="mt-[0.4em]">{t}</p>)}{all.map((t, i) => <p key={i} className="mt-[0.4em]">{t}</p>)}</div>
              </div>
            </div>
            <p className="mt-2 text-xs text-neutral-500">Drag the dashed box or use the controls. This preview is approximate — the exact layout is in the PDF preview. Longer text continues on a second sheet.</p>
          </div>
          <aside className="space-y-4">
            <div className="space-y-3 rounded-xl border border-line bg-white p-4 text-sm">
              {([["Left", "x", 0, 0.5], ["Top", "y", 0, 0.8], ["Width", "width", 0.3, 1], ["Text size", "font_scale", 0.6, 1.6]] as const).map(([l, k, mn, mx]) => (
                <label key={k} className="block"><span className="mb-1 flex justify-between font-medium"><span>{l}</span><span className="text-neutral-500">{k === "font_scale" ? `${Math.round(place[k] * 100)}%` : `${Math.round(place[k] * 100)}`}</span></span>
                  <input type="range" className="w-full accent-[#12372A]" min={mn} max={mx} step={0.01} value={place[k]} onChange={(e) => setPlace({ ...place, [k]: Number(e.target.value) })} /></label>))}
              <button className="btn btn-ghost w-full !py-1.5" onClick={() => setPlace(DEFAULT)}>Reset position</button>
            </div>
            <button className="btn btn-primary w-full" onClick={create} disabled={busy}>{busy ? <Loader2 className="animate-spin" size={16} /> : <FileImage size={16} />} Create stamp paper PDF</button>
            <button className="btn btn-ghost w-full" onClick={() => { setPhase("idle"); setFile(null); setUrl(""); }}><RefreshCw size={16} /> Replace image</button>
          </aside>
        </div>)}
      <p className="mt-6 max-w-2xl text-xs text-neutral-500">Page 1 uses your stamp paper. If the document is longer, the following pages are plain white paper.</p>
      <div className="mt-4 flex gap-6 text-sm">
        <button className="text-neutral-600 underline underline-offset-2 hover:text-ink" onClick={onBack}>Back to Edit &amp; Review</button>
        <button className="text-neutral-600 underline underline-offset-2 hover:text-ink" onClick={onSkip}>Skip — I only need the standard PDF</button>
      </div>
    </div>
  );
}
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
