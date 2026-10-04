"use client";
import { useState } from "react";
import { ArrowDown, ArrowUp, Check, Loader2, Plus, Trash2 } from "lucide-react";
import type { Content } from "@/types";

type ListKey = "meta" | "intro" | "clauses" | "extra_clauses";

/** Simple block editor for the generated draft. The edited JSON is the final document: it is rendered as-is, never re-sent to the AI. */
export default function Editor({ content, allowExtra, busy, onApply, onBack }: { content: Content; allowExtra: boolean; busy: boolean; onApply: (c: Content) => void; onBack: () => void }) {
  const [c, setC] = useState<Content>(() => ({ ...JSON.parse(JSON.stringify(content)), extra_clauses: content.extra_clauses ?? [], extra_title: content.extra_title ?? "" }));
  const [err, setErr] = useState("");
  const ur = c.rtl;
  const cls = `input ${ur ? "font-urdu" : ""}`;
  const dir = ur ? "rtl" : "ltr";
  const rows = (t: string) => Math.max(2, Math.ceil(t.length / (ur ? 60 : 85)));
  const L = ur ? { clause: "شق", extra: "اضافی شرائط / شقیں" } : { clause: "Clause", extra: "Additional Terms / Clauses" };

  const setList = (k: ListKey, f: (a: string[]) => string[]) => setC((p) => ({ ...p, [k]: f([...(p[k] || [])]) }));
  const edit = (k: ListKey, i: number, v: string) => setList(k, (a) => a.map((x, j) => (j === i ? v : x)));
  const del = (k: ListKey, i: number) => setList(k, (a) => a.filter((_, j) => j !== i));
  const move = (k: ListKey, i: number, d: number) => setList(k, (a) => { const j = i + d; if (j < 0 || j >= a.length) return a; [a[i], a[j]] = [a[j], a[i]]; return a; });
  const add = (k: ListKey) => setList(k, (a) => [...a, ""]);

  function Blocks({ k, label, numberFrom = 0, canDelete = true }: { k: ListKey; label: string; numberFrom?: number; canDelete?: boolean }) {
    const items = c[k] || [];
    return (
      <div className="space-y-3">
        {items.map((t, i) => (
          <div key={i} className="rounded-xl border border-line bg-white p-3">
            <div className="mb-2 flex items-center justify-between gap-2 text-sm">
              <span className="font-medium text-ink">{label} {numberFrom + i + 1}</span>
              <span className="flex gap-1">
                <button type="button" className="btn btn-ghost !px-2 !py-1" aria-label="Move up" onClick={() => move(k, i, -1)} disabled={i === 0}><ArrowUp size={14} /></button>
                <button type="button" className="btn btn-ghost !px-2 !py-1" aria-label="Move down" onClick={() => move(k, i, 1)} disabled={i === items.length - 1}><ArrowDown size={14} /></button>
                {canDelete && <button type="button" className="btn btn-ghost !px-2 !py-1 text-red-700" aria-label={`Delete ${label} ${numberFrom + i + 1}`} onClick={() => del(k, i)}><Trash2 size={14} /> Delete</button>}
              </span>
            </div>
            <textarea className={cls} dir={dir} rows={rows(t)} value={t} aria-label={`${label} ${numberFrom + i + 1}`} onChange={(e) => edit(k, i, e.target.value)} />
          </div>))}
      </div>
    );
  }

  function apply() {
    if (!c.title.trim()) { setErr("The document needs a title."); return; }
    if (c.signers.some((s) => !s[1].trim())) { setErr("Every signer needs a name."); return; }
    setErr(""); onApply(c);
  }
  const Sec = ({ title, children, hint }: { title: string; children: React.ReactNode; hint?: string }) => (
    <section className="mt-8"><h2 className="font-display text-lg font-semibold text-ink">{title}</h2>{hint && <p className="mb-2 text-sm text-neutral-500">{hint}</p>}<div className="mt-2">{children}</div></section>);
  const addBtn = (k: ListKey, label: string) => <button type="button" className="btn btn-ghost mt-3 !py-1.5" onClick={() => add(k)}><Plus size={15} /> {label}</button>;

  return (
    <div>
      <h1 className="font-display text-3xl font-bold text-ink">Review and edit your document</h1>
      <p className="mt-1 max-w-2xl text-neutral-600">This draft was written by AI. Edit any text, delete clauses you don&apos;t want, or add your own. Your version is final — it is used exactly as written and is not sent to the AI again.</p>

      <div className="mt-6 max-w-3xl rounded-2xl border border-line bg-paper p-5">
        <Sec title="Heading"><input className={`${cls} text-center font-semibold`} dir={dir} value={c.title} aria-label="Document title" onChange={(e) => setC({ ...c, title: e.target.value })} /></Sec>
        {c.meta.length > 0 && <Sec title="Details">{c.meta.map((m, i) => <input key={i} className={`${cls} mb-2`} dir={dir} value={m} aria-label={`Detail ${i + 1}`} onChange={(e) => edit("meta", i, e.target.value)} />)}</Sec>}
        <Sec title="Introduction" hint="Parties and key details. Check names, CNICs, addresses, dates and amounts."><Blocks k="intro" label={ur ? "پیراگراف" : "Paragraph"} canDelete={false} /></Sec>
        <Sec title={ur ? "شرائط و ضوابط" : "Terms and Conditions"}><Blocks k="clauses" label={L.clause} />{addBtn("clauses", "Add clause")}</Sec>
        {(allowExtra || (c.extra_clauses?.length ?? 0) > 0) && (
          <Sec title={L.extra} hint="Clauses you entered for this agreement.">
            {(c.extra_clauses?.length ?? 0) > 0 && <input className={`${cls} mb-3`} dir={dir} value={c.extra_title || ""} aria-label="Additional clauses heading" onChange={(e) => setC({ ...c, extra_title: e.target.value })} />}
            <Blocks k="extra_clauses" label={L.clause} numberFrom={c.clauses.length} />{addBtn("extra_clauses", "Add additional clause")}
          </Sec>)}
        <Sec title={ur ? "اختتامی پیراگراف" : "Closing"}><textarea className={cls} dir={dir} rows={rows(c.closing)} value={c.closing} aria-label="Closing paragraph" onChange={(e) => setC({ ...c, closing: e.target.value })} /></Sec>
        <Sec title={ur ? "دستخط" : "Signatures"} hint="Text printed under each signature line.">
          <div className="grid gap-3 sm:grid-cols-2">
            {c.signers.map((s, i) => (
              <div key={i} className="space-y-2 rounded-xl border border-line bg-white p-3">
                {["Role", "Name", "CNIC"].map((l, j) => <label key={j} className="block text-xs font-medium text-neutral-600">{l}<input className={`${cls} mt-1 text-sm`} dir={j === 2 ? "ltr" : dir} style={j === 2 ? { unicodeBidi: "isolate" } : undefined} value={s[j]} onChange={(e) => setC({ ...c, signers: c.signers.map((x, a) => (a === i ? x.map((y, b) => (b === j ? e.target.value : y)) : x)) })} /></label>)}
              </div>))}
          </div>
        </Sec>
        <Sec title={ur ? "گواہان" : "Witnesses"}>
          <div className="grid gap-3 sm:grid-cols-2">
            {c.witnesses.map((w, i) => (
              <div key={i} className="space-y-2 rounded-xl border border-line bg-white p-3">
                {["Name", "CNIC"].map((l, j) => <label key={j} className="block text-xs font-medium text-neutral-600">{l}<input className={`${cls} mt-1 text-sm`} dir={j === 1 ? "ltr" : dir} style={j === 1 ? { unicodeBidi: "isolate" } : undefined} value={w[j]} onChange={(e) => setC({ ...c, witnesses: c.witnesses.map((x, a) => (a === i ? x.map((y, b) => (b === j ? e.target.value : y)) : x)) })} /></label>)}
                <button type="button" className="btn btn-ghost !px-2 !py-1 text-red-700" onClick={() => setC({ ...c, witnesses: c.witnesses.filter((_, a) => a !== i) })}><Trash2 size={14} /> Remove witness</button>
              </div>))}
          </div>
          {c.witnesses.length < 4 && <button type="button" className="btn btn-ghost mt-3 !py-1.5" onClick={() => setC({ ...c, witnesses: [...c.witnesses, ["", ""]] })}><Plus size={15} /> Add witness</button>}
        </Sec>
      </div>
      {err && <p role="alert" className="mt-4 max-w-3xl rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{err}</p>}
      <div className="mt-6 flex max-w-3xl justify-between">
        <button className="btn btn-ghost" onClick={onBack} disabled={busy}>Start over</button>
        <button className="btn btn-primary" onClick={apply} disabled={busy}>{busy ? <Loader2 className="animate-spin" size={16} /> : <Check size={16} />} Apply edits &amp; continue</button>
      </div>
    </div>
  );
}
