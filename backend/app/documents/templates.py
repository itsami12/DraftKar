"""Deterministic templates: structured data + LLM clauses -> content dict for the PDF engine."""
from datetime import datetime

TITLES = {
    "rent_agreement": ("RENT AGREEMENT", "کرایہ نامہ"), "affidavit": ("AFFIDAVIT", "حلف نامہ"),
    "undertaking": ("UNDERTAKING", "اقرار نامہ"), "authority_letter": ("AUTHORITY LETTER (MUKHTARNAMA)", "مختارنامہ"),
}
L = {
    "english": dict(sig="Signature", name="Name", cnic="CNIC", wit="Witnesses", date="Date", subject="Subject", page="Page",
                    Landlord="Landlord", Tenant="Tenant", Deponent="Deponent", Executant="Person giving undertaking",
                    Principal="Principal (Grantor)", Agent="Authorized person (Attorney)"),
    "urdu": dict(sig="دستخط", name="نام", cnic="شناختی کارڈ نمبر", wit="گواہان", date="تاریخ", subject="موضوع", page="صفحہ",
                 Landlord="مالک مکان", Tenant="کرایہ دار", Deponent="حلف دہندہ", Executant="اقرار کنندہ",
                 Principal="مختار دہندہ", Agent="مختار (نامزد شخص)"),
}


LRI, PDI = "\u2066", "\u2069"  # invisible LTR isolate: keeps numbers like 35202-9876543-0 in order inside RTL text


def _date(v, lang):
    try:
        d = datetime.strptime(v, "%Y-%m-%d")
        return d.strftime("%d %B %Y") if lang == "english" else f"{LRI}{d.strftime('%d-%m-%Y')}{PDI}"
    except Exception:
        return v


def _money(v):
    try:
        return f"{int(float(str(v).replace(',', ''))):,}"
    except Exception:
        return v


def _p(a, k, lang):
    """Party description. A document says where the person is *residing*, so it uses the CURRENT address only.
    The permanent address is never merged into this sentence; see _permanent_para()."""
    n, f, c, ad = a[f"{k}_name"], a[f"{k}_father"], a[f"{k}_cnic"], a[f"{k}_current_address"]
    if lang == "english":
        return f"{n} S/O {f}, CNIC No. {c}, currently residing at {ad}"
    return f"{n} ولد {f}، شناختی کارڈ نمبر {LRI}{c}{PDI}، موجودہ پتہ: {ad}"


# (form-field prefix, label key) of the parties of each document, in signing order
PARTIES = {"rent_agreement": [("landlord", "Landlord"), ("tenant", "Tenant")], "affidavit": [("deponent", "Deponent")],
           "undertaking": [("person", "Executant")], "authority_letter": [("principal", "Principal"), ("agent", "Agent")]}


def _permanent_para(doc_type, a, lang, lab):
    """Own, clearly labelled paragraph with each party's PERMANENT address (only parties who gave one). None if nobody did."""
    rows = [(lab[role], a[f"{k}_name"], a.get(f"{k}_permanent_address", "").strip()) for k, role in PARTIES[doc_type]]
    rows = [r for r in rows if r[2]]
    if not rows:
        return None
    if lang == "english":
        return " ".join(f"Permanent address of the {r} ({n}): {ad}." for r, n, ad in rows)
    return " ".join(f"{r} ({n}) کا مستقل پتہ: {ad}۔" for r, n, ad in rows)


def build(doc_type, lang, a, out):
    clauses = out.clauses
    en = lang == "english"
    lab = L[lang]
    title = TITLES[doc_type][0 if en else 1]
    meta, intro, signers, closing = [], [], [], ""
    if doc_type == "rent_agreement":
        d, rent, dep = _date(a["start_date"], lang), _money(a["monthly_rent"]), _money(a["security_deposit"])
        if en:
            intro = [f'This Rent Agreement is made on {d} between {_p(a, "landlord", lang)} (hereinafter called the "Landlord") '
                     f'and {_p(a, "tenant", lang)} (hereinafter called the "Tenant").',
                     f"The Landlord lets the property situated at {a['property_address']} to the Tenant for a period of {a['duration']} "
                     f"commencing from {d}, at a monthly rent of Rs. {rent}/- and a refundable security deposit of Rs. {dep}/-.",
                     "The parties agree to the following terms and conditions:"]
            closing = "IN WITNESS WHEREOF the parties have signed this Agreement on the date first written above."
        else:
            intro = [f"یہ کرایہ نامہ مورخہ {d} کو {_p(a, 'landlord', lang)} (جسے آئندہ ”مالک مکان“ کہا جائے گا) اور "
                     f"{_p(a, 'tenant', lang)} (جسے آئندہ ”کرایہ دار“ کہا جائے گا) کے درمیان طے پایا۔",
                     f"مالک مکان نے جائیداد واقع {a['property_address']} کرایہ دار کو {a['duration']} کی مدت کے لیے، مورخہ {d} سے، "
                     f"ماہانہ کرایہ {rent} روپے اور قابلِ واپسی سیکیورٹی ڈپازٹ {dep} روپے پر کرایہ پر دی ہے۔",
                     "فریقین درج ذیل شرائط پر متفق ہیں:"]
            closing = "فریقین نے مندرجہ بالا تاریخ کو اپنے دستخط ثبت کیے۔"
        signers = [(lab["Landlord"], a["landlord_name"], a["landlord_cnic"]), (lab["Tenant"], a["tenant_name"], a["tenant_cnic"])]
    elif doc_type == "affidavit":
        meta = [f"{lab['subject']}: {a['purpose']}", f"{lab['date']}: {_date(a['date'], lang)}"]
        intro = [f"I, {_p(a, 'deponent', lang)}, do hereby solemnly affirm and declare on oath as under:" if en else
                 f"میں، {_p(a, 'deponent', lang)}، حلفاً بیان کرتا/کرتی ہوں کہ:"]
        closing = ("VERIFICATION: Verified on oath that the contents of this affidavit are true and correct to the best of my knowledge and belief, "
                   "and nothing has been concealed therein." if en else
                   "تصدیق: میں حلفاً تصدیق کرتا/کرتی ہوں کہ اس حلف نامے کے مندرجات میرے علم و یقین کے مطابق درست ہیں اور ان میں کوئی بات پوشیدہ نہیں رکھی گئی۔")
        signers = [(lab["Deponent"], a["deponent_name"], a["deponent_cnic"])]
    elif doc_type == "undertaking":
        meta = [f"{lab['subject']}: {a['subject']}", f"{lab['date']}: {_date(a['date'], lang)}"]
        intro = [f"I, {_p(a, 'person', lang)}, do hereby solemnly undertake as follows:" if en else
                 f"میں، {_p(a, 'person', lang)}، بقائمی ہوش و حواس درج ذیل اقرار کرتا/کرتی ہوں:"]
        closing = ("I confirm that this undertaking is given of my own free will and I shall remain bound by it." if en else
                   "میں تصدیق کرتا/کرتی ہوں کہ یہ اقرار نامہ میں نے اپنی مرضی سے تحریر کیا ہے اور میں اس کا پابند رہوں گا/گی۔")
        signers = [(lab["Executant"], a["person_name"], a["person_cnic"])]
    else:
        meta = [f"{lab['date']}: {_date(a['date'], lang)}"]
        dur = a.get("duration", "")
        if en:
            intro = [f"I, {_p(a, 'principal', lang)} (the \"Principal\"), do hereby appoint {_p(a, 'agent', lang)} (the \"Attorney\") "
                     f"as my true and lawful attorney to act on my behalf for the following purpose: {a['purpose']}."
                     + (f" This authority is valid for: {dur}." if dur else ""),
                     "The Attorney is authorized to do the following acts:"]
            closing = "I undertake to accept and ratify all lawful acts done by the Attorney within the scope of this authority."
        else:
            intro = [f"میں، {_p(a, 'principal', lang)} (”مختار دہندہ“)، {_p(a, 'agent', lang)} (”مختار“) کو اپنی جانب سے "
                     f"درج ذیل مقصد کے لیے اپنا مختارِ خاص مقرر کرتا/کرتی ہوں: {a['purpose']}۔"
                     + (f" یہ اختیار {dur} تک مؤثر رہے گا۔" if dur else ""),
                     "مختار کو درج ذیل امور سرانجام دینے کا اختیار ہوگا:"]
            closing = "میں اس اختیار کی حدود میں مختار کے تمام قانونی اقدامات کو تسلیم اور منظور کرتا/کرتی ہوں۔"
        signers = [(lab["Principal"], a["principal_name"], a["principal_cnic"]), (lab["Agent"], a["agent_name"], a["agent_cnic"])]
    perm = _permanent_para(doc_type, a, lang, lab)
    if perm:  # separate labelled paragraph right after the parties' paragraph; never merged into the parties' sentence
        intro.insert(1, perm)
    # the user's own core text is shown verbatim as the first clause so facts are never altered by the LLM
    core = {"affidavit": "declaration", "undertaking": "commitment", "authority_letter": "scope"}.get(doc_type)
    all_clauses = ([a[core]] if core else []) + list(clauses)
    if doc_type == "undertaking" and a.get("conditions"):
        all_clauses.append(a["conditions"])
    if doc_type == "rent_agreement" and a.get("utilities"):
        all_clauses.insert(0, a["utilities"])
    witnesses = [(a.get(f"w{i}_name", ""), a.get(f"w{i}_cnic", "")) for i in (1, 2)]
    extras = list(out.additional_clauses) if doc_type == "rent_agreement" else []
    extra_title = ("Additional Terms / Clauses" if en else "اضافی شرائط / شقیں") if extras else ""
    return dict(extra_title=extra_title, extra_clauses=extras, title=title, meta=meta, intro=intro, clauses=all_clauses, closing=closing, signers=signers,
                witnesses=[w for w in witnesses if w[0]], labels=lab, rtl=not en)
