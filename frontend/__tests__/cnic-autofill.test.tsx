import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InfoStep } from "@/components/Wizard";
import type { CnicResult, DocSpec, Lang } from "@/types";

// The network layer is the only thing mocked: extractCnic stands in for FastAPI + OCR.Space.
const extractCnic = vi.fn();
vi.mock("@/lib/api", () => ({ extractCnic: (...a: unknown[]) => extractCnic(...a) }));

const person = (p: string, en: string) => [
  { key: `${p}_name`, en: `${en} full name`, ur: "نام", type: "text", required: true, section: p },
  { key: `${p}_father`, en: `${en}'s father's name`, ur: "والد", type: "text", required: true, section: p },
  { key: `${p}_cnic`, en: `${en} CNIC`, ur: "شناختی کارڈ", type: "cnic", required: true, section: p },
  { key: `${p}_address`, en: `${en} address`, ur: "پتہ", type: "textarea", required: true, section: p },
];
const SPEC = {
  document_type: "rent_agreement", en: "Rent Agreement", ur: "کرایہ نامہ", desc: "",
  sections: [{ id: "landlord", en: "Landlord", ur: "مالک مکان" }, { id: "tenant", en: "Tenant", ur: "کرایہ دار" }],
  fields: [...person("landlord", "Landlord"), ...person("tenant", "Tenant")],
} as DocSpec;

const result = (fields: Partial<CnicResult["fields"]>, message = ""): CnicResult => ({
  ok: true, message, needs_review: ["address"], confidence: {},
  fields: { name: null, father_name: null, cnic: null, date_of_birth: null, gender: null, address: null, ...fields },
});
const LANDLORD = result({ name: "Muhammad Ahmed Khan", father_name: "Abdul Rehman Khan", cnic: "35202-9876543-0", date_of_birth: "12-04-1998", gender: "Male" });
const TENANT = result({ name: "Ali Hassan Malik", father_name: "Muhammad Ashraf Malik", cnic: null }, "Please verify CNIC number");

let submitted: Record<string, string> | null = null;
function Harness({ lang = "english", initial = {} }: { lang?: Lang; initial?: Record<string, string> }) {
  const [answers, setAnswers] = useState<Record<string, string>>(initial);
  return (<>
    <InfoStep spec={SPEC} lang={lang} answers={answers} setAnswers={setAnswers} onBack={() => {}} onSubmit={() => { submitted = answers; }} />
    <output data-testid="answers">{JSON.stringify(answers)}</output>
  </>);
}
const answers = () => JSON.parse(screen.getByTestId("answers").textContent || "{}") as Record<string, string>;
const png = () => new File([new Uint8Array([137, 80, 78, 71])], "cnic.png", { type: "image/png" });
const value = (re: RegExp) => (screen.getByLabelText(re) as HTMLInputElement).value;

async function upload(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, png());
  return screen.findByRole("region", { name: /CNIC information extracted/i });
}

beforeEach(() => { extractCnic.mockReset(); submitted = null; });

describe("CNIC upload -> review -> apply", () => {
  it("test 6: landlord fields auto-populate, but only after Apply Information", async () => {
    extractCnic.mockResolvedValueOnce(LANDLORD);
    const user = userEvent.setup(); render(<Harness />);
    const panel = await upload(user);
    expect(extractCnic).toHaveBeenCalledTimes(1);
    expect(value(/^Landlord full name/)).toBe("");                        // review panel is showing; the form is still untouched
    expect(answers()).toEqual({});
    expect(within(panel).getByLabelText(/^CNIC Number/)).toHaveValue("35202-9876543-0");
    expect(within(panel).getByText(/valid format/i)).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: /apply information/i }));
    expect(value(/^Landlord full name/)).toBe("Muhammad Ahmed Khan");
    expect(value(/^Landlord's father/)).toBe("Abdul Rehman Khan");
    expect(value(/^Landlord CNIC/)).toBe("35202-9876543-0");
    expect(screen.queryByRole("region", { name: /CNIC information extracted/i })).not.toBeInTheDocument();
  });

  it("cancel applies nothing", async () => {
    extractCnic.mockResolvedValueOnce(LANDLORD);
    const user = userEvent.setup(); render(<Harness />);
    const panel = await upload(user);
    await user.click(within(panel).getByRole("button", { name: /cancel/i }));
    expect(answers()).toEqual({});
  });

  it("unreadable/ambiguous CNIC: field left blank, flagged 'Please verify CNIC number'", async () => {
    extractCnic.mockResolvedValueOnce(TENANT);
    const user = userEvent.setup(); render(<Harness />);
    const panel = await upload(user);
    expect(within(panel).getByLabelText(/^CNIC Number/)).toHaveValue("");
    expect(within(panel).getAllByText(/please verify cnic number/i).length).toBeGreaterThan(0);
  });

  it("extraction failure shows the message and leaves manual entry available", async () => {
    extractCnic.mockResolvedValueOnce({ ...result({}), ok: false, message: "Could not confidently read the CNIC. Please upload a clearer image or enter the information manually." });
    const user = userEvent.setup(); render(<Harness />);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, png());
    expect(await screen.findByRole("alert")).toHaveTextContent(/clearer image/i);
    await user.type(screen.getByLabelText(/^Landlord full name/), "Typed By Hand");
    expect(answers().landlord_name).toBe("Typed By Hand");
  });

  it("rejects non-image files in the browser before any request", async () => {
    const user = userEvent.setup({ applyAccept: false }); render(<Harness />);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, new File(["x"], "c.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/JPG, JPEG, PNG, or WebP/);
    expect(extractCnic).not.toHaveBeenCalled();
  });

  it("blank extracted values never erase what the user already typed", async () => {
    extractCnic.mockResolvedValueOnce(result({ name: "Muhammad Ahmed Khan" }));
    const user = userEvent.setup(); render(<Harness initial={{ landlord_address: "House 25, Jhelum" }} />);
    const panel = await upload(user);
    await user.clear(within(panel).getByLabelText(/^Address/));
    await user.click(within(panel).getByRole("button", { name: /apply information/i }));
    expect(answers().landlord_name).toBe("Muhammad Ahmed Khan");
    expect(answers().landlord_address).toBe("House 25, Jhelum");
  });
});

describe("multiple parties and manual edits", () => {
  it("tests 7 + 8: tenant upload leaves landlord untouched, and user edits reach the final answers", async () => {
    extractCnic.mockResolvedValueOnce(LANDLORD).mockResolvedValueOnce(TENANT);
    const user = userEvent.setup(); render(<Harness />);

    // Landlord: edit in the review panel (add address), apply, then edit the form by hand.
    let panel = await upload(user);
    await user.type(within(panel).getByLabelText(/^Address/), "House 25, Street 4, Gulshan Colony, Jhelum");
    await user.click(within(panel).getByRole("button", { name: /apply information/i }));
    await user.clear(screen.getByLabelText(/^Landlord full name/));
    await user.type(screen.getByLabelText(/^Landlord full name/), "Muhammad Ahmed Khan (edited)");
    const landlordBefore = Object.fromEntries(Object.entries(answers()).filter(([k]) => k.startsWith("landlord_")));
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Tenant: CNIC could not be read -> user types the number in reversed (RTL) group order; Apply repairs it.
    panel = await upload(user);
    await user.type(within(panel).getByLabelText(/^CNIC Number/), "7-2468135-35202");
    await user.type(within(panel).getByLabelText(/^Address/), "House 18, Street 7, Fareed Town, Jhelum");
    await user.click(within(panel).getByRole("button", { name: /apply information/i }));

    const a = answers();
    expect(a.tenant_name).toBe("Ali Hassan Malik");
    expect(a.tenant_cnic).toBe("35202-2468135-7");                       // canonical LTR, not the reversed text that was typed
    expect(a.tenant_address).toBe("House 18, Street 7, Fareed Town, Jhelum");
    expect(Object.fromEntries(Object.entries(a).filter(([k]) => k.startsWith("landlord_")))).toEqual(landlordBefore);  // landlord unchanged
    expect(a.landlord_name).toBe("Muhammad Ahmed Khan (edited)");
    expect(a.landlord_cnic).toBe("35202-9876543-0");

    await user.click(screen.getByRole("button", { name: /generate document/i }));
    expect(submitted).toMatchObject({ landlord_name: "Muhammad Ahmed Khan (edited)", landlord_cnic: "35202-9876543-0", tenant_cnic: "35202-2468135-7" });
  });
});

describe("Urdu / RTL", () => {
  it("CNIC inputs stay left-to-right and isolated inside an RTL form and review panel", async () => {
    extractCnic.mockResolvedValueOnce(LANDLORD);
    const user = userEvent.setup(); const { container } = render(<Harness lang="urdu" />);
    expect(container.firstElementChild).toHaveAttribute("dir", "rtl");
    const formCnic = container.querySelector("#landlord_cnic") as HTMLInputElement;
    expect(formCnic).toHaveAttribute("dir", "ltr");
    expect(formCnic.style.unicodeBidi).toBe("isolate");
    const panel = await upload(user);
    const panelCnic = within(panel).getAllByRole("textbox")[2] as HTMLInputElement;   // name, father, CNIC
    expect(panelCnic).toHaveValue("35202-9876543-0");
    expect(panelCnic).toHaveAttribute("dir", "ltr");
    expect(panelCnic.style.unicodeBidi).toBe("isolate");
    await user.click(within(panel).getByRole("button", { name: "معلومات لاگو کریں" }));
    await waitFor(() => expect(formCnic).toHaveValue("35202-9876543-0"));  // stored canonical, never "0-9876543-35202"
  });
});
