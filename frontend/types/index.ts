export type Lang = "english" | "urdu";
export type DocMeta = { type: string; en: string; ur: string; desc: string };
export type Field = { key: string; en: string; ur: string; type: "text" | "textarea" | "number" | "date" | "cnic" | "clauses"; required: boolean; section: string };
export type Section = { id: string; en: string; ur: string };
export type DocSpec = Omit<DocMeta, "type"> & { document_type: string; fields: Field[]; sections: Section[] };
export type Content = { title: string; meta: string[]; intro: string[]; clauses: string[]; extra_title?: string; extra_clauses?: string[]; closing: string; signers: string[][]; witnesses: string[][]; labels: Record<string, string>; rtl: boolean };
export type CnicFields = { name: string | null; father_or_husband_name: string | null; cnic: string | null; date_of_birth: string | null; gender: string | null; current_address: string | null; permanent_address: string | null };
export type CnicSideStatus = "ok" | "missing" | "failed" | "unreadable";
/** ONE profile for ONE person, combined from the front (identity) and back (current + permanent address) images. */
export type CnicResult = { ok: boolean; message: string; warnings: string[]; status: { front: CnicSideStatus; back: CnicSideStatus }; fields: CnicFields; confidence: Record<string, string | null>; needs_review: string[]; latin?: Record<string, string>;
  /** fields = canonical values as printed on the card. presentation = the same person rendered for each document language (name, father, both addresses, gender); CNIC number and date are language-independent. */
  presentation?: { en: Partial<CnicFields>; ur: Partial<CnicFields> };
  success?: boolean; error_code?: string; retry_after?: number };
export type Placement = { x: number; y: number; width: number; font_scale: number };
export type Region = { text: string; x: number; y: number; width: number; height: number };
export type StampAnalysis = { ok: boolean; message: string; text: string; regions: Region[]; image: { width: number; height: number }; suggested: Placement };
