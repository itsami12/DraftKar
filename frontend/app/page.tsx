"use client";
import { useEffect, useState } from "react";
import { LogOut, ArrowLeft } from "lucide-react";
import Login from "@/components/Login";
import Dashboard from "@/components/Dashboard";
import Preview from "@/components/Preview";
import Editor from "@/components/Editor";
import StampStep from "@/components/StampStep";
import { Generating, InfoStep, LanguageStep, Progress } from "@/components/Wizard";
import { ApiError, generate, getDoc, getToken, listDocs, renderStandard, setToken } from "@/lib/api";
import type { Content, DocMeta, DocSpec, Lang } from "@/types";

export default function Home() {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [step, setStep] = useState(1);
  const [spec, setSpec] = useState<DocSpec | null>(null);
  const [lang, setLang] = useState<Lang | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [pdf, setPdf] = useState("");
  const [content, setContent] = useState<Content | null>(null);
  const [stamp, setStamp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const logout = () => { setToken(null); setAuthed(false); reset(); };
  const loadDocs = () => listDocs().then((d) => { setDocs(d); setAuthed(true); }).catch(() => setAuthed(false));
  useEffect(() => { (getToken() ? loadDocs() : Promise.resolve()).finally(() => setReady(true)); }, []);

  function reset() { if (pdf) URL.revokeObjectURL(pdf); if (stamp) URL.revokeObjectURL(stamp); setPdf(""); setStamp(""); setContent(null); setStep(1); setSpec(null); setLang(null); setAnswers({}); setError(""); }
  async function pickDoc(d: DocMeta) { try { setSpec(await getDoc(d.type)); setStep(2); setError(""); } catch (e: any) { setError(e.message); if (e.status === 401) logout(); } }
  async function submit() {
    if (!spec || !lang) return; setStep(4); setError("");
    try { const r = await generate(spec.document_type, lang, answers); setContent(r.content); setStep(5); }
    catch (e) { setError(e instanceof ApiError ? e.message : "We couldn't generate the document right now. Please try again."); setStep(3); }
  }
  async function approve(c: Content) {
    if (!spec) return; setBusy(true); setError("");
    try {
      const blob = await renderStandard(spec.document_type, c);  // no AI call: the edited content is final
      if (pdf) URL.revokeObjectURL(pdf); if (stamp) URL.revokeObjectURL(stamp);
      setPdf(URL.createObjectURL(blob)); setStamp(""); setContent(c); setStep(6);
    } catch (e: any) { setError(e.message || "We couldn't create the PDF right now. Please try again."); } finally { setBusy(false); }
  }
  if (!ready) return null;
  if (!authed) return <Login onDone={loadDocs} />;
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div><div className="font-display text-xl font-bold text-ink">DraftKar</div><div className="text-xs text-neutral-500">Document Preparation</div></div>
          <div className="flex items-center gap-3 text-sm"><span className="hidden text-neutral-500 sm:inline">Signed in</span>
            <button className="btn btn-ghost !py-1.5" onClick={logout}><LogOut size={15} /> Logout</button></div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <Progress step={step} extra={spec ? spec.en : undefined} />
        {error && <p role="alert" className="mb-6 max-w-2xl rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
        {step === 1 && <Dashboard docs={docs} onSelect={pickDoc} />}
        {step === 2 && spec && (<>
          <LanguageStep value={lang} onPick={(l) => { setLang(l); setStep(3); }} />
          <button className="btn btn-ghost mt-6" onClick={reset}><ArrowLeft size={16} /> Back</button></>)}
        {step === 3 && spec && lang && <InfoStep spec={spec} lang={lang} answers={answers} setAnswers={setAnswers} onBack={() => setStep(2)} onSubmit={submit} />}
        {step === 4 && <Generating />}
        {step === 5 && spec && content && <Editor key={spec.document_type + lang} content={content} allowExtra={spec.document_type === "rent_agreement"} busy={busy} onApply={approve} onBack={reset} />}
        {step === 6 && spec && content && <StampStep docType={spec.document_type} content={content} onBack={() => setStep(5)} onDone={(u) => { if (stamp) URL.revokeObjectURL(stamp); setStamp(u); setStep(7); }} onSkip={() => setStep(7)} />}
        {step === 7 && spec && lang && <Preview stdUrl={pdf} stampUrl={stamp} title={spec.en} lang={lang} onReset={reset} onStamp={() => setStep(6)} onEdit={() => setStep(5)} />}
        <p className="mt-12 max-w-2xl border-t border-line pt-4 text-xs text-neutral-500">This tool assists with document preparation. Review the generated document carefully before printing, signing, or submitting it.</p>
      </main>
    </div>
  );
}
