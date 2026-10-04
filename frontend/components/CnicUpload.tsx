"use client";
import { useEffect, useRef, useState } from "react";
import { IdCard, Loader2, AlertCircle, CheckCircle2, Upload, X } from "lucide-react";
import CnicExtractionReview from "./CnicExtractionReview";
import { extractCnic } from "@/lib/api";
import { localizeMsg, rateLimitMsg } from "@/lib/cnicText";
import type { CnicFields, CnicResult } from "@/types";

const OK = ["image/jpeg", "image/png", "image/webp"];
const BAD = "Please upload a JPG, JPEG, PNG, or WebP image under 10 MB.";
const FAIL = "We couldn't read the CNIC right now. Please try again, upload clearer images, or enter the information manually.";
type Side = "front" | "back";

/** One instance per party (landlord, tenant, ...): each keeps its own files/result and only ever applies to its own fields.
 *  Front + back are uploaded separately, read separately by the backend and returned as ONE profile for ONE person. */
export default function CnicUpload({ party, ur, applied, onApply }: { party: string; ur: boolean; applied: boolean; onApply: (f: CnicFields) => void }) {
  const [files, setFiles] = useState<Record<Side, File | null>>({ front: null, back: null });
  const [urls, setUrls] = useState<Record<Side, string>>({ front: "", back: "" });  // local previews only; never uploaded
  const [phase, setPhase] = useState<"idle" | "reading" | "review">("idle");
  const [result, setResult] = useState<CnicResult | null>(null);
  const [err, setErr] = useState("");
  const [warn, setWarn] = useState<string[]>([]);
  const [step, setStep] = useState(0);  // which progress message is active while the backend works (front/back are read in parallel)
  const urlsRef = useRef(urls); urlsRef.current = urls;
  const busy = useRef(false);                       // synchronous guard: a second click in the same tick can never start a second request
  const [cool, setCool] = useState(false);          // short lock after a rate-limit answer so the button cannot be hammered
  const coolTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (coolTimer.current) clearTimeout(coolTimer.current); }, []);
  function startCool(sec?: number) { setCool(true); if (coolTimer.current) clearTimeout(coolTimer.current); coolTimer.current = setTimeout(() => setCool(false), Math.min(Math.max(sec ?? 15, 5), 60) * 1000); }
  useEffect(() => { if (phase !== "reading") { setStep(0); return; } const t = setInterval(() => setStep((n) => n + 1), 2600); return () => clearInterval(t); }, [phase]);
  useEffect(() => () => { Object.values(urlsRef.current).forEach((u) => u && URL.revokeObjectURL(u)); }, []);

  function set(side: Side, f: File | null) {
    setUrls((u) => { if (u[side]) URL.revokeObjectURL(u[side]); return { ...u, [side]: f ? URL.createObjectURL(f) : "" }; });
    setFiles((s) => ({ ...s, [side]: f })); setErr(""); setWarn([]);
  }
  function pick(side: Side, f?: File | null) {
    if (!f) return;
    if (!OK.includes(f.type) || f.size > 10 * 1024 * 1024) { setErr(localizeMsg(BAD, ur)); return; }
    set(side, f);
  }
  function clearAll() { set("front", null); set("back", null); }

  const both = !!files.front && !!files.back, any = !!files.front || !!files.back;
  const canExtract = phase !== "reading" && both && !cool;  // both sides are required: they are read together in ONE request
  async function extract() {
    if (busy.current || cool) return;               // one click = exactly one POST /cnic/extract
    busy.current = true;
    setErr(""); setWarn([]); setPhase("reading");
    try {
      const r = await extractCnic(files.front, files.back, ur);
      if (!r.ok) {
        if (r.error_code === "GROQ_RATE_LIMIT") { setErr(rateLimitMsg(ur)); setWarn([]); startCool(r.retry_after); }   // no automatic retry: the user retries
        else { setErr(localizeMsg(r.message || FAIL, ur)); setWarn(r.warnings.filter((w) => w !== r.message).map((w) => localizeMsg(w, ur))); }
        setPhase("idle"); return;
      }
      setResult(r); setPhase("review");
    } catch (e: any) { setErr(e.status === 400 ? localizeMsg(e.message, ur) : localizeMsg(FAIL, ur)); setPhase("idle"); }
    finally { busy.current = false; }
  }

  const T = ur
    ? { title: "شناختی کارڈ کی معلومات", sub: `${party} — شناختی شناخت اور پتے کی معلومات حاصل کرنے کے لیے شناختی کارڈ کے دونوں رخ اپ لوڈ کریں۔ تصاویر محفوظ نہیں کی جاتیں۔`, front: "سامنے کا رخ", back: "پچھلا رخ", frontBtn: "شناختی کارڈ کا سامنے والا رخ اپ لوڈ کریں", backBtn: "شناختی کارڈ کا پچھلا رخ اپ لوڈ کریں",
        formats: "JPG / PNG / WebP", go: "شناختی کارڈ کی معلومات حاصل کریں", busy: "معلومات حاصل کی جا رہی ہیں…", both: "معلومات حاصل کرنے کے لیے دونوں رخ اپ لوڈ کریں (پتے پچھلے رخ پر ہوتے ہیں)", replace: "تبدیل کریں",
        up: ["✓ سامنے کا رخ اپ لوڈ ہو گیا", "✓ پچھلا رخ اپ لوڈ ہو گیا"], steps: ["دونوں رخ کا تجزیہ کیا جا رہا ہے…", "نام اور شناختی نمبر پڑھا جا رہا ہے…", "موجودہ اور مستقل پتہ پڑھا جا رہا ہے…"], done: "معلومات لاگو ہو گئیں — براہ کرم دوبارہ جانچ لیں۔" }
    : { title: "CNIC INFORMATION", sub: `${party} — upload both sides of the CNIC to extract identity and address information. Images are read once and not stored.`, front: "FRONT SIDE", back: "BACK SIDE", frontBtn: "Upload Front", backBtn: "Upload Back",
        formats: "JPG / PNG / WebP", go: "Extract CNIC Information", busy: "Extracting...", both: "Upload both sides to extract identity and address information (the addresses are on the back).", replace: "Replace",
        up: ["✓ Front side uploaded", "✓ Back side uploaded"], steps: ["Analyzing both sides of the CNIC...", "Reading name and CNIC number...", "Reading current and permanent address..."], done: "Details applied — you can still edit every field below." };

  const zone = (side: Side) => {
    const f = files[side];
    return (
      <div key={side}>
        <p className="mb-1.5 text-xs font-semibold tracking-wide text-neutral-600">{side === "front" ? T.front : T.back}</p>
        <label className={`relative flex min-h-[9.5rem] cursor-pointer flex-col items-center justify-center gap-1 overflow-hidden rounded-2xl border-2 border-dashed p-3 text-center transition ${f ? "border-green-600/60 bg-green-50/40" : "border-line bg-white hover:border-ink"} ${phase === "reading" ? "pointer-events-none opacity-70" : ""}`}
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(side, e.dataTransfer.files?.[0]); }}>
          <input type="file" hidden accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" aria-label={`${party} ${side === "front" ? "CNIC front" : "CNIC back"}`}
            onChange={(e) => { pick(side, e.target.files?.[0]); e.target.value = ""; }} />
          {f && urls[side]
            ? <><img src={urls[side]} alt="" className="max-h-24 rounded-md object-contain" /><span className="max-w-full truncate text-xs text-neutral-600">{f.name}</span><span className="text-xs font-medium text-ink underline">{T.replace}</span></>
            : <><Upload size={22} className="text-stamp" aria-hidden /><span className="text-sm font-medium text-ink">{side === "front" ? T.frontBtn : T.backBtn}</span><span className="text-xs text-neutral-500">{T.formats}</span></>}
        </label>
        {f && phase !== "reading" && <button type="button" className="mt-1 flex items-center gap-1 text-xs text-neutral-500 hover:text-red-700" onClick={() => set(side, null)}><X size={12} />{ur ? "ہٹائیں" : "Remove"}</button>}
      </div>);
  };

  return (
    <div className="mt-6 max-w-2xl">
      {phase !== "review" && (
        <section aria-label="CNIC upload" className="rounded-2xl border border-dashed border-line bg-white px-5 py-4">
          <div className="flex items-start gap-3"><IdCard className="mt-0.5 shrink-0 text-stamp" size={26} aria-hidden />
            <div className="text-sm"><h2 className="font-semibold tracking-wide text-ink">{T.title}</h2><p className="text-neutral-500">{T.sub}</p></div></div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2" dir="ltr">{zone("front")}{zone("back")}</div>
          {(files.front || files.back) && (
            <ul className="mt-3 space-y-0.5 text-sm text-green-700" aria-live="polite">{files.front && <li>{T.up[0]}</li>}{files.back && <li>{T.up[1]}</li>}</ul>)}
          {phase === "reading" && (() => {
            const msgs = T.steps, cur = Math.min(step, msgs.length - 1);
            return (
              <ul role="status" aria-live="polite" className="mt-2 space-y-1 text-sm font-medium text-ink">
                {msgs.slice(0, cur + 1).map((m, i) => <li key={m} className={`flex items-center gap-2 ${i === cur ? "" : "text-neutral-500"}`}>{i === cur ? <Loader2 className="animate-spin" size={14} /> : <CheckCircle2 size={14} className="text-green-600" />}{m}</li>)}
              </ul>);
          })()}
          {any && !both && phase !== "reading" && <p className="mt-2 text-sm text-amber-800">{T.both}</p>}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button type="button" className="btn btn-primary" disabled={!canExtract} onClick={extract}>{phase === "reading" ? <Loader2 className="animate-spin" size={16} /> : <IdCard size={16} />}{phase === "reading" ? T.busy : T.go}</button>
            {any && phase !== "reading" && <button type="button" className="text-sm text-neutral-500 hover:text-ink" onClick={clearAll}>{ur ? "صاف کریں" : "Clear"}</button>}
          </div>
        </section>)}
      {applied && phase === "idle" && !err && !any && <p className="mt-2 flex items-center gap-2 text-sm text-green-700"><CheckCircle2 size={15} />{T.done}</p>}
      {err && <div role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"><p className="flex items-center gap-2"><AlertCircle size={15} />{err}</p>{warn.map((w) => <p key={w} className="mt-1 pl-6">{w}</p>)}</div>}
      {phase === "review" && result && <CnicExtractionReview result={result} ur={ur} onCancel={() => setPhase("idle")} onApply={(f) => { onApply(f); setPhase("idle"); setResult(null); clearAll(); }} />}
    </div>
  );
}
