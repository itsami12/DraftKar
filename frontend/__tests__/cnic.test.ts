import { describe, expect, it } from "vitest";
import { isCanonicalCnic, normalizeCnic } from "@/lib/cnic";

// Client-side mirror of backend/tests/test_cnic.py (spec tests 1-5). The backend is the source of truth.
describe("normalizeCnic", () => {
  it("test 1: keeps an English-order CNIC", () => expect(normalizeCnic("35202-9876543-0")).toBe("35202-9876543-0"));
  it("test 2: reorders RTL-reversed groups", () => expect(normalizeCnic("0-9876543-35202")).toBe("35202-9876543-0"));
  it("test 3: reorders another reversed CNIC", () => expect(normalizeCnic("7-2468135-35202")).toBe("35202-2468135-7"));
  it("test 4: never reverses a correct CNIC again", () => expect(normalizeCnic("35202-2468135-7")).toBe("35202-2468135-7"));
  it("test 5: invalid -> null", () => expect(normalizeCnic("1234-5678")).toBeNull());
  it("never reverses digits inside a group", () => expect(normalizeCnic("0-9876543-35202")?.split("-")[1]).toBe("9876543"));
  it("accepts Azad Kashmir (8) and rejects impossible leading digits", () => {
    expect(normalizeCnic("1-1234567-81202")).toBe("81202-1234567-1");
    expect(normalizeCnic("95202-9876543-0")).toBeNull();
    expect(isCanonicalCnic("05202-9876543-0")).toBe(false);
  });
  it("handles OCR noise and Arabic-Indic digits", () => {
    expect(normalizeCnic(" 35202 – 9876543 — 0 ")).toBe("35202-9876543-0");
    expect(normalizeCnic("٣٥٢٠٢-٩٨٧٦٥٤٣-٠")).toBe("35202-9876543-0");
  });
  it("ambiguous input -> null", () => {
    expect(normalizeCnic("3520298765430")).toBeNull();
    expect(normalizeCnic("35202-9876543-05")).toBeNull();
  });
});
