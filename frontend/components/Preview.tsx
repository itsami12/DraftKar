"use client";
import { useState } from "react";
import { Download, RotateCcw, Printer, FileImage, Pencil } from "lucide-react";
import Img from "./Img";

export default function Preview({ stdUrl, stampUrl, title, lang, onReset, onStamp, onEdit }: { stdUrl: string; stampUrl: string; title: string; lang: string; onReset: () => void; onStamp: () => void; onEdit: () => void }) {
  const [tab, setTab] = useState<"std" | "stamp">(stampUrl ? "stamp" : "std");
  const url = tab === "stamp" && stampUrl ? stampUrl : stdUrl;
  const base = `${title.replace(/\s+/g, "_")}_${lang}`;
  return (
    <div>
      <h1 className="font-display text-3xl font-bold text-ink">Document ready</h1>
      <p className="mt-1 text-neutral-600">{title} · Language: {lang === "urdu" ? "Urdu" : "English"}</p>
      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_280px]">
        <div>
          <div role="tablist" className="mb-3 inline-flex rounded-lg border border-line bg-white p-1 text-sm">
            {([["std", "Standard document"], ["stamp", "Stamp paper"]] as const).map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} disabled={k === "stamp" && !stampUrl} onClick={() => setTab(k)}
                className={`rounded-md px-4 py-1.5 font-medium disabled:opacity-40 ${tab === k ? "bg-ink text-white" : "text-ink"}`}>{l}</button>))}
          </div>
          <div className="overflow-hidden rounded-2xl border border-line bg-neutral-200 p-2 shadow-sm"><iframe key={url} title="PDF preview" src={url} className="h-[75vh] w-full rounded-lg bg-white" /></div>
        </div>
        <aside className="space-y-3">
          <a href={stdUrl} download={`${base}.pdf`} className="btn btn-primary w-full"><Download size={16} /> Download standard PDF</a>
          {stampUrl ? <a href={stampUrl} download={`${base}_stamp_paper.pdf`} className="btn btn-primary w-full"><Download size={16} /> Download stamp paper PDF</a>
            : <button onClick={onStamp} className="btn btn-ghost w-full"><FileImage size={16} /> Add stamp paper</button>}
          <button onClick={onEdit} className="btn btn-ghost w-full"><Pencil size={16} /> Edit document</button>
          <button onClick={onReset} className="btn btn-ghost w-full"><RotateCcw size={16} /> Start over</button>
          <div className="rounded-xl border border-line bg-white p-4 text-sm text-neutral-600">
            <Img src="/images/printer.png" alt="Printer" className="mb-3 h-24 w-full object-contain" />
            <div className="flex items-center gap-2 font-medium text-ink"><Printer size={15} /> Printing</div>
            <p className="mt-1">Direct printing is planned for a future version. Both PDFs contain your approved text exactly as edited.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
