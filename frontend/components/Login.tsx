"use client";
import { useState } from "react";
import { Loader2, ShieldCheck } from "lucide-react";
import Img from "./Img";
import { login } from "@/lib/api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(""); setBusy(true);
    try { await login(u, p); onDone(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }
  return (
    <main className="grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
      <section className="relative flex flex-col justify-between overflow-hidden bg-stamp/90 p-8 lg:p-12">
        <Img src="/images/stamp-paper.png" alt="Pakistani stamp paper" className="absolute inset-0 h-full w-full object-cover opacity-90" />
        <div className="absolute inset-0 bg-gradient-to-t from-ink/90 via-ink/30 to-transparent" />
        <div className="relative font-display text-2xl font-bold text-white drop-shadow">DraftKar</div>
        <div className="relative max-w-lg text-white">
          <h2 className="font-display text-3xl font-semibold leading-tight lg:text-4xl">From a few answers to a document ready for the stamp paper.</h2>
          <p className="mt-3 text-white/85">Rent agreements, affidavits, undertakings and mukhtarnamas — in English or Urdu.</p>
        </div>
      </section>
      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-4xl font-bold text-ink">DraftKar</h1>
          <p className="mt-2 font-medium text-ink">AI-powered document preparation for Pakistani document writers.</p>
          <p className="mt-2 text-sm text-neutral-600">Prepare structured, professional documents faster — from information collection to ready-to-download PDF.</p>
          <form onSubmit={submit} className="mt-8 space-y-4 rounded-2xl border border-line bg-white p-6">
            <div><label htmlFor="u" className="mb-1 block text-sm font-medium">Username</label>
              <input id="u" className="input" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" required /></div>
            <div><label htmlFor="p" className="mb-1 block text-sm font-medium">Password</label>
              <input id="p" type="password" className="input" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></div>
            {err && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}
            <button className="btn btn-primary w-full" disabled={busy}>{busy ? <Loader2 className="animate-spin" size={16} /> : <ShieldCheck size={16} />} Sign in</button>
          </form>
        </div>
      </section>
    </main>
  );
}
