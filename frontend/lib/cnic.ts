// Client-side mirror of the backend's CNIC rules, used only for the review panel's ✓ indicator and for
// tidying what the user types. The backend re-normalizes on generate; the canonical form is always XXXXX-XXXXXXX-X (left-to-right).
const AR = "٠١٢٣٤٥٦٧٨٩", FA = "۰۱۲۳۴۵۶۷۸۹";
const ascii = (s: string) => s.replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, "").replace(/[٠-٩]/g, (d) => String(AR.indexOf(d))).replace(/[۰-۹]/g, (d) => String(FA.indexOf(d))).replace(/[\u2010-\u2015\u2212_]/g, "-");
export const isCanonicalCnic = (v: string) => /^[1-7]\d{4}-\d{7}-\d$/.test(v);
/** 5-7-1 is kept; 1-7-5 (RTL group-order reversal) is reordered to 5-7-1; digits inside groups are never reversed. Anything else -> null. */
export function normalizeCnic(raw: string): string | null {
  const m = ascii(raw).trim().match(/^(\d{5}|\d)[-\s]+(\d{7})[-\s]+(\d{5}|\d)$/);
  if (!m) return null;
  const [, a, b, c] = m;
  const out = a.length === 5 && c.length === 1 ? `${a}-${b}-${c}` : a.length === 1 && c.length === 5 ? `${c}-${b}-${a}` : null;
  return out && isCanonicalCnic(out) ? out : null;
}
