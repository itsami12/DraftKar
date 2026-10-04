"use client";
import { useState } from "react";
import { ArrowLeft, ArrowRight, Check, Loader2, Plus, X } from "lucide-react";
import CnicUpload from "./CnicUpload";
import type { CnicFields, DocSpec, Field, Lang } from "@/types";

export const STEPS = ["Document", "Language", "Information", "Generate", "Edit & Review", "Stamp Paper", "Final Preview"];

export function Progress({ step, extra }: { step: number; extra?: string }) {
  return (
    <div className="mb-8">
      <ol className="flex items-center gap-2 overflow-x-auto text-sm">
        {STEPS.map((s, i) => (
          <li key={s} className={`flex items-center gap-2 whitespace-nowrap ${i + 1 === step ? "font-semibold text-ink" : i + 1 < step ? "text-ink/70" : "text-neutral-400"}`}>
            <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${i + 1 < step ? "bg-ink text-white" : i + 1 === step ? "border-2 border-ink" : "border border-line"}`}>{i + 1 < step ? <Check size={13} /> : i + 1}</span>{s}
            {i < STEPS.length - 1 && <span className="h-px w-5 bg-line" />}
          </li>))}
      </ol>
      <p className="mt-3 text-sm text-neutral-600">Step {step} of {STEPS.length} — {STEPS[step - 1]}{extra ? ` · ${extra}` : ""}</p>
    </div>
  );
}

export function LanguageStep({ value, onPick }: { value: Lang | null; onPick: (l: Lang) => void }) {
  const opts: { l: Lang; title: string; sub: string; urdu?: boolean }[] = [
    { l: "english", title: "English", sub: "Professional English document" },
    { l: "urdu", title: "اردو", sub: "اردو میں دستاویز تیار کریں", urdu: true }];
  return (
    <div>
      <h1 className="font-display text-3xl font-bold text-ink">Select document language</h1>
      <div className="mt-6 grid max-w-2xl gap-4 sm:grid-cols-2" role="radiogroup">
        {opts.map((o) => (
          <button key={o.l} role="radio" aria-checked={value === o.l} onClick={() => onPick(o.l)}
            className={`rounded-2xl border-2 p-6 text-left transition ${value === o.l ? "border-ink bg-ink text-white" : "border-line bg-white hover:border-ink"}`}>
            <div className={`text-2xl font-semibold ${o.urdu ? "font-urdu" : "font-display"}`} dir={o.urdu ? "rtl" : undefined}>{o.title}</div>
            <div className={`mt-1 text-sm ${value === o.l ? "text-white/80" : "text-neutral-600"} ${o.urdu ? "font-urdu" : ""}`} dir={o.urdu ? "rtl" : undefined}>{o.sub}</div>
          </button>))}
      </div>
    </div>
  );
}

export function InfoStep({ spec, lang, answers, setAnswers, onBack, onSubmit }: {
  spec: DocSpec; lang: Lang; answers: Record<string, string>; setAnswers: (a: Record<string, string>) => void; onBack: () => void; onSubmit: () => void;
}) {
  const [i, setI] = useState(0); const [err, setErr] = useState("");
  // one identity object per party (landlord, tenant, ...) so one upload can never overwrite another party
  const [parties, setParties] = useState<Record<string, CnicFields>>({});
  const [useAddr, setUseAddr] = useState<Record<string, "current_address" | "permanent_address">>({});  // which CNIC address goes into the document, per party
  const ur = lang === "urdu"; const sec = spec.sections[i];
  const fields = spec.fields.filter((f) => f.section === sec.id);
  const last = i === spec.sections.length - 1;
  function next() {
    if (fields.some((f) => f.required && !(answers[f.key] || "").trim())) { setErr(ur ? "براہ کرم تمام ضروری خانے مکمل کریں۔" : "Please complete all required fields."); return; }
    setErr(""); last ? onSubmit() : setI(i + 1);
  }
  const person = fields.some((f) => f.key === `${sec.id}_cnic`);
  function applyCnic(p: string, id: CnicFields) {
    setParties((s) => ({ ...s, [p]: id }));
    // Only ONE address goes into the document (the user's choice, default Current); the other stays in the party profile and is never merged in.
    const pick = useAddr[p] || "current_address";
    const map: [string, string | null][] = [[`${p}_name`, id.name], [`${p}_father`, id.father_or_husband_name], [`${p}_cnic`, id.cnic], [`${p}_current_address`, id[pick]]];
    setAnswers({ ...answers, ...Object.fromEntries(map.filter(([, v]) => v) as [string, string][]) });  // only values that exist; blanks never erase what the user typed
  }
  function chooseAddr(p: string, k: "current_address" | "permanent_address") {
    setUseAddr((s) => ({ ...s, [p]: k }));
    const v = parties[p]?.[k]; if (v) setAnswers({ ...answers, [`${p}_current_address`]: v });
  }
  const addrChoice = (p: string) => {
    const id = parties[p]; if (!id || (!id.current_address && !id.permanent_address)) return null;
    const cur = useAddr[p] || "current_address";
    const opt = (k: "current_address" | "permanent_address", en: string, urd: string) => (
      <label key={k} className={`flex items-start gap-2 text-sm ${id[k] ? "" : "opacity-50"}`}>
        <input type="radio" name={`addr-${p}`} className="mt-1" checked={cur === k} disabled={!id[k]} onChange={() => chooseAddr(p, k)} />
        <span>{ur ? urd : en} <span className="font-urdu text-neutral-500" dir="rtl">{ur ? en : urd}</span>{!id[k] && <span className="text-neutral-500">{ur ? " — پڑھا نہیں گیا" : " — not detected"}</span>}</span>
      </label>);
    return (
      <fieldset className="mt-4 max-w-2xl rounded-2xl border border-line bg-white p-4">
        <legend className="px-1 text-sm font-semibold">{ur ? "دستاویز میں استعمال ہونے والا پتہ" : "Address to use in document"}</legend>
        <div className="space-y-1.5">{opt("current_address", "Current Address", "موجودہ پتہ")}{opt("permanent_address", "Permanent Address", "مستقل پتہ")}</div>
        <p className="mt-2 text-xs text-neutral-500">{ur ? "صرف منتخب پتہ دستاویز میں جائے گا؛ آپ اسے نیچے خانے میں تبدیل کر سکتے ہیں۔" : "Only the selected address is placed in the document. You can still edit it below."}</p>
      </fieldset>);
  };
  const input = (f: Field) => {
    const common = { id: f.key, className: "input", value: answers[f.key] || "", onChange: (e: any) => setAnswers({ ...answers, [f.key]: e.target.value }), required: f.required, "aria-required": f.required };
    if (f.type === "clauses") return <ClauseList id={f.key} value={answers[f.key] || ""} ur={ur} onChange={(v) => setAnswers({ ...answers, [f.key]: v })} />;
    if (f.type === "textarea") return <textarea rows={3} {...common} />;
    if (f.type === "date") return <input type="date" {...common} dir="ltr" />;
    if (f.type === "number") return <input type="number" min={0} inputMode="numeric" {...common} dir="ltr" />;
    return <input type="text" {...common} placeholder={f.type === "cnic" ? "35202-1234567-1" : ""} dir={f.type === "cnic" ? "ltr" : undefined} style={f.type === "cnic" ? { unicodeBidi: "isolate", direction: "ltr" } : undefined} />;
  };
  return (
    <div dir={ur ? "rtl" : "ltr"} lang={ur ? "ur" : "en"} className={ur ? "font-urdu" : ""}>
      <h1 className="font-display text-2xl font-bold text-ink">{ur ? sec.ur : sec.en}</h1>
      <p className="mt-1 text-sm text-neutral-600">{ur ? `حصہ ${i + 1} از ${spec.sections.length}` : `Part ${i + 1} of ${spec.sections.length}`}</p>
      {person && <CnicUpload key={sec.id} party={ur ? sec.ur : sec.en} ur={ur} applied={!!parties[sec.id]} onApply={(f) => applyCnic(sec.id, f)} />}
      {person && addrChoice(sec.id)}
      <div className="mt-6 grid max-w-2xl gap-5 rounded-2xl border border-line bg-white p-6">
        {fields.map((f) => (
          <div key={f.key}>
            <label htmlFor={f.key} className="mb-1 block text-sm font-medium">{ur ? f.ur : f.en}{f.required ? <span className="text-stamp"> *</span> : <span className="text-neutral-400">{ur ? " (اختیاری)" : " (optional)"}</span>}</label>
            {input(f)}
          </div>))}
        {err && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}
      </div>
      <div className="mt-6 flex max-w-2xl justify-between" dir="ltr">
        <button className="btn btn-ghost" onClick={() => (i === 0 ? onBack() : setI(i - 1))}><ArrowLeft size={16} /> Back</button>
        <button className="btn btn-primary" onClick={next}>{last ? "Generate document" : "Continue"} <ArrowRight size={16} /></button>
      </div>
    </div>
  );
}

function ClauseList({ id, value, ur, onChange }: { id: string; value: string; ur: boolean; onChange: (v: string) => void }) {
  const [items, setItems] = useState<string[]>(value ? value.split("\n") : [""]);
  const set = (n: string[]) => { setItems(n); onChange(n.join("\n")); };
  return (
    <div className="space-y-2">
      <p className="text-sm text-neutral-500">{ur ? "کرائے کے معاہدے میں شامل کرنے کے لیے کوئی اضافی شرائط درج کریں۔" : "Add any additional terms or conditions you want included in the rent agreement."}</p>
      {items.map((it, i) => (
        <div key={i} className="flex gap-2">
          <input id={i === 0 ? id : undefined} className="input" value={it} aria-label={`${ur ? "شق" : "Clause"} ${i + 1}`} placeholder={`${ur ? "شق" : "Clause"} ${i + 1}`}
            onChange={(e) => set(items.map((x, j) => (j === i ? e.target.value : x)))} />
          {items.length > 1 && <button type="button" className="btn btn-ghost !px-3" aria-label="Remove clause" onClick={() => set(items.filter((_, j) => j !== i))}><X size={16} /></button>}
        </div>))}
      <button type="button" className="btn btn-ghost !py-1.5" onClick={() => set([...items, ""])} disabled={items.length >= 15}><Plus size={15} /> {ur ? "ایک اور شق شامل کریں" : "Add another clause"}</button>
    </div>
  );
}

export function Generating() {
  return (<div className="flex flex-col items-center py-24 text-center" role="status"><Loader2 className="animate-spin text-ink" size={36} />
    <h1 className="mt-6 font-display text-2xl font-bold text-ink">Preparing your document…</h1>
    <p className="mt-2 text-neutral-600">Drafting the clauses and formatting the PDF. This usually takes a few seconds.</p></div>);
}
