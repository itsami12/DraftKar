"use client";
import { useState } from "react";
import { AlertCircle, Check, CheckCircle2 } from "lucide-react";
import { isCanonicalCnic, normalizeCnic } from "@/lib/cnic";
import { localizeMsg } from "@/lib/cnicText";
import type { CnicFields, CnicResult } from "@/types";

type Row = { k: keyof CnicFields; en: string; ur: string; sub?: string; ltr?: boolean; area?: boolean };
const IDENTITY: Row[] = [
  { k: "name", en: "Full Name", ur: "پورا نام" }, { k: "father_or_husband_name", en: "Father / Husband Name", ur: "والد / شوہر کا نام" },
  { k: "cnic", en: "CNIC Number", ur: "شناختی کارڈ نمبر", ltr: true }, { k: "date_of_birth", en: "Date of Birth", ur: "تاریخ پیدائش", ltr: true },
  { k: "gender", en: "Gender", ur: "جنس" }];
// the two addresses are different things and are never merged: each has its own field, label and warning
const ADDRESS: Row[] = [
  { k: "current_address", en: "Current Address", ur: "موجودہ پتہ", sub: "موجودہ پتہ", area: true },
  { k: "permanent_address", en: "Permanent Address", ur: "مستقل پتہ", sub: "مستقل پتہ", area: true }];
const ALL = [...IDENTITY, ...ADDRESS];
const URDU = /[\u0600-\u06FF]/;
const LANG_FREE: (keyof CnicFields)[] = ["cnic", "date_of_birth"];  // numbers are identical in both languages and never translated
const NOT_DETECTED = { en: "Not detected — enter manually", ur: "معلوم نہیں ہو سکا — دستی طور پر درج کریں" };

/** Nothing reaches the form until the user clicks Apply Information. Every value is editable; missing/uncertain ones are flagged. */
export default function CnicExtractionReview({ result, ur, onApply, onCancel }: { result: CnicResult; ur: boolean; onApply: (f: CnicFields) => void; onCancel: () => void }) {
  // Canonical values (result.fields, as printed on the card) are never modified. The form shows the rendering for the selected language
  // (result.presentation[lang]); `edits` holds ONLY what the user typed, so switching language never overwrites a user edit.
  const lang = ur ? "ur" : "en";
  const [edits, setEdits] = useState<Record<string, string>>({});
  const shown = (k: keyof CnicFields) => (LANG_FREE.includes(k) ? result.fields[k] : result.presentation?.[lang]?.[k] ?? result.fields[k]) ?? "";
  const val = (k: keyof CnicFields) => edits[k] ?? shown(k);
  const printedOnly = (k: keyof CnicFields) => !LANG_FREE.includes(k) && !(k in edits) && !!result.presentation && !!result.fields[k] && !result.presentation[lang]?.[k];  // no rendering available: printed value shown, flagged
  const cnicOk = isCanonicalCnic(val("cnic").trim()) || !!normalizeCnic(val("cnic"));
  function apply() {
    const typed = val("cnic").trim(); const fixed = typed ? normalizeCnic(typed) : "";  // a reversed group order typed by the user is repaired; unknown formats stay as typed
    onApply(Object.fromEntries(ALL.map((r) => [r.k, r.k === "cnic" ? (fixed ?? typed) || null : val(r.k).trim() || null])) as CnicFields);
  }
  const got = (k: keyof CnicFields) => !!result.fields[k];
  const idOk = got("name") || got("cnic");
  const lines: { ok: boolean; text: string }[] = ur
    ? [{ ok: idOk, text: idOk ? "✓ شناختی معلومات حاصل ہو گئیں" : "⚠ شناختی معلومات پڑھی نہیں جا سکیں۔" },
       { ok: got("current_address"), text: got("current_address") ? "✓ موجودہ پتہ حاصل ہو گیا" : "⚠ موجودہ پتہ یقین سے نہیں پڑھا جا سکا۔ براہ کرم خود درج کریں۔" },
       { ok: got("permanent_address"), text: got("permanent_address") ? "✓ مستقل پتہ حاصل ہو گیا" : "⚠ مستقل پتہ یقین سے نہیں پڑھا جا سکا۔ براہ کرم خود درج کریں۔" }]
    : [{ ok: idOk, text: idOk ? "✓ Identity information extracted" : "⚠ Could not read the identity information." },
       { ok: got("current_address") && result.confidence?.current_address !== "low", text: got("current_address") ? (result.confidence?.current_address === "low" ? "⚠ Current address read with low confidence — please check it." : "✓ Current address extracted") : "⚠ Could not confidently read current address. Please review or enter it manually." },
       { ok: got("permanent_address") && result.confidence?.permanent_address !== "low", text: got("permanent_address") ? (result.confidence?.permanent_address === "low" ? "⚠ Permanent address read with low confidence — please check it." : "✓ Permanent address extracted") : "⚠ Could not confidently read permanent address. Please review or enter it manually." }];

  const field = (r: Row) => {
    const v = val(r.k), empty = !v.trim(), edited = r.k in edits, printed = printedOnly(r.k);
    // CNIC: flagged until valid. Others: flagged when empty, still the uncertain extracted value (editing counts as reviewing), or shown only as printed.
    const review = r.k === "cnic" ? !cnicOk : empty || printed || (result.needs_review.includes(r.k) && !edited);
    const urduText = URDU.test(v);
    const low = r.area && result.confidence?.[r.k] === "low" && !edited && !empty;  // uncertain read, not yet edited by the user
    const ph = empty ? NOT_DETECTED[lang] : r.k === "cnic" ? "35202-1234567-1" : "";
    const set = (x: string) => setEdits({ ...edits, [r.k]: x });
    const badge = r.k === "cnic" ? (ur ? "براہ کرم نمبر کی تصدیق کریں" : "Please verify CNIC number")
      : printed ? (ur ? "کارڈ پر درج صورت میں — براہ کرم اردو میں درست کریں" : "Shown as printed on the card — please convert to English")
      : result.latin?.[r.k] ? (ur ? "تجویز کردہ ہجے — کارڈ پر لکھے نام سے ملائیں" : "Suggested spelling — compare with your card")
      : ur ? "جائزہ درکار ہے" : "Needs review";
    return (
      <label key={r.k} className={`block text-sm font-medium ${r.area ? "sm:col-span-2" : ""}`}>
        <span className="flex flex-wrap items-center gap-2">{ur ? r.ur : r.en}{r.sub && !ur && <span className="font-urdu text-base text-neutral-500" dir="rtl">{r.sub}</span>}
          {r.k === "cnic" && cnicOk && <span className="inline-flex items-center gap-1 text-xs font-semibold text-green-700"><Check size={13} />{ur ? "درست فارمیٹ" : "valid format"}</span>}
          {result.latin?.[r.k] && <span className="text-xs font-normal text-neutral-500" dir="ltr">{ur ? "کارڈ پر: " : "On card: "}{result.latin[r.k]}</span>}
          {low && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-semibold text-red-800">{ur ? "کم اعتماد — براہ کرم ضرور جانچیں" : "Low confidence — please check carefully"}</span>}
          {review && !low && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">{badge}</span>}</span>
        {r.area
          ? <textarea rows={3} className={`input mt-1 ${urduText ? "font-urdu" : ""}`} dir="auto" placeholder={ph} value={v} onChange={(e) => set(e.target.value)} />
          : <input className={`input mt-1 ${urduText && !r.ltr ? "font-urdu" : ""}`} value={v} onChange={(e) => set(e.target.value)} dir={r.ltr ? "ltr" : ur ? "rtl" : "ltr"} style={r.ltr ? { unicodeBidi: "isolate", direction: "ltr" } : undefined} placeholder={ph} />}
      </label>);
  };
  return (
    <div role="region" aria-label="CNIC information extracted" className="rounded-2xl border-2 border-stamp/60 bg-white p-5">
      <h3 className="font-display text-lg font-semibold text-ink">{ur ? "شناختی کارڈ کی معلومات کی جانچ" : "REVIEW CNIC INFORMATION"}</h3>
      <p className="mt-1 text-sm text-neutral-600">{ur ? "براہ کرم ہر خانے کی جانچ کریں اور ضرورت ہو تو درست کریں۔ ‘معلومات لاگو کریں’ دبانے تک فارم میں کچھ نہیں بھرا جائے گا۔" : "Check every field and correct anything that is wrong. Nothing is added to the form until you click Apply Information."}</p>
      <p className="mt-3 flex flex-wrap gap-4 text-sm font-medium" aria-label="Sides read">
        {(["front", "back"] as const).map((sd) => <span key={sd} className={result.status[sd] === "ok" ? "text-green-700" : "text-amber-800"}>{ur ? (sd === "front" ? "سامنے کا رخ" : "پچھلا رخ") : (sd === "front" ? "Front" : "Back")} {result.status[sd] === "ok" ? "✓" : "⚠"}</span>)}
      </p>
      <ul className="mt-3 space-y-1 text-sm" aria-label="Extraction status">
        {lines.map((l, i) => <li key={i} className={`flex items-start gap-2 ${l.ok ? "text-green-700" : "text-amber-800"}`}>{l.ok ? <CheckCircle2 size={15} className="mt-0.5 shrink-0" /> : <AlertCircle size={15} className="mt-0.5 shrink-0" />}<span>{l.text.replace(/^[✓⚠]\s*/, "")}</span></li>)}
      </ul>
      {/* backend messages that the three lines above do not already say (missing side, failed read, blurry image, ambiguous addresses...) */}
      {result.warnings.filter((w) => !/Current address could not|Permanent address could not/.test(w)).map((w) => <p key={w} role="alert" className="mt-2 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800"><AlertCircle size={15} className="mt-0.5 shrink-0" />{localizeMsg(w, ur)}</p>)}
      <h4 className="mt-5 text-sm font-semibold tracking-wide text-ink">{ur ? "شناختی معلومات" : "Identity Information"}</h4>
      <div className="mt-2 grid gap-4 sm:grid-cols-2">{IDENTITY.map(field)}</div>
      <h4 className="mt-6 text-sm font-semibold tracking-wide text-ink">{ur ? "پتے کی معلومات" : "ADDRESS INFORMATION"}</h4>
      <div className="mt-2 grid gap-4 sm:grid-cols-2">{ADDRESS.map(field)}</div>
      <div className="mt-5 flex flex-wrap gap-3">
        <button type="button" className="btn btn-primary" onClick={apply}><Check size={16} />{ur ? "معلومات لاگو کریں" : "Apply Information"}</button>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>{ur ? "منسوخ کریں" : "Cancel"}</button>
      </div>
    </div>
  );
}
