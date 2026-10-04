"""Document definitions: the single source of truth for question forms (served to the frontend)."""

DOCS = {
    "rent_agreement": {"en": "Rent Agreement", "ur": "کرایہ نامہ",
                       "desc": "Prepare structured rental agreements with landlord, tenant, property, rent and duration details."},
    "affidavit": {"en": "Affidavit", "ur": "حلف نامہ",
                  "desc": "Prepare declaration-based affidavits from structured information."},
    "undertaking": {"en": "Undertaking", "ur": "اقرار نامہ",
                    "desc": "Prepare formal undertakings and declarations."},
    "authority_letter": {"en": "Authority Letter", "ur": "مختارنامہ",
                         "desc": "Prepare an authorization document for granting authority to another person."},
}


def person(prefix, section, en, ur):
    return [
        (f"{prefix}_name", f"{en} full name", f"{ur} کا پورا نام", "text", True, section),
        (f"{prefix}_father", f"{en}'s father's name", f"{ur} کے والد کا نام", "text", True, section),
        (f"{prefix}_cnic", f"{en} CNIC", f"{ur} کا شناختی کارڈ نمبر", "cnic", True, section),
        (f"{prefix}_current_address", f"{en} current address", f"{ur} کا موجودہ پتہ", "textarea", True, section),
        (f"{prefix}_permanent_address", f"{en} permanent address", f"{ur} کا مستقل پتہ", "textarea", False, section),
    ]


WITNESS = [
    ("w1_name", "Witness 1 name", "گواہ نمبر 1 کا نام", "text", False, "witnesses"),
    ("w1_cnic", "Witness 1 CNIC", "گواہ نمبر 1 کا شناختی کارڈ نمبر", "cnic", False, "witnesses"),
    ("w2_name", "Witness 2 name", "گواہ نمبر 2 کا نام", "text", False, "witnesses"),
    ("w2_cnic", "Witness 2 CNIC", "گواہ نمبر 2 کا شناختی کارڈ نمبر", "cnic", False, "witnesses"),
]
S_WIT = ("witnesses", "Witnesses", "گواہان")

DEFS = {
    "rent_agreement": {
        "sections": [("landlord", "Landlord", "مالک مکان"), ("tenant", "Tenant", "کرایہ دار"),
                     ("terms", "Property & rent", "جائیداد اور کرایہ"), S_WIT],
        "fields": person("landlord", "landlord", "Landlord", "مالک مکان") + person("tenant", "tenant", "Tenant", "کرایہ دار") + [
            ("property_address", "Property address", "جائیداد کا پتہ", "textarea", True, "terms"),
            ("monthly_rent", "Monthly rent (PKR)", "ماہانہ کرایہ (روپے)", "number", True, "terms"),
            ("security_deposit", "Security deposit (PKR)", "سیکیورٹی ڈپازٹ (روپے)", "number", True, "terms"),
            ("duration", "Agreement duration (e.g. 11 months)", "معاہدے کی مدت (مثلاً 11 ماہ)", "text", True, "terms"),
            ("start_date", "Start date", "آغاز کی تاریخ", "date", True, "terms"),
            ("utilities", "Utility / payment responsibilities", "یوٹیلیٹی بلز / ادائیگی کی ذمہ داریاں", "textarea", False, "terms"),
            ("additional_clauses", "Additional clauses (optional)", "اضافی شقیں (اختیاری)", "clauses", False, "terms"),
        ] + WITNESS,
    },
    "affidavit": {
        "sections": [("deponent", "Deponent", "حلف دہندہ"), ("declaration", "Declaration", "بیان"), S_WIT],
        "fields": person("deponent", "deponent", "Deponent", "حلف دہندہ") + [
            ("purpose", "Subject / purpose of affidavit", "حلف نامے کا موضوع / مقصد", "text", True, "declaration"),
            ("declaration", "Declaration details", "بیان کی تفصیل", "textarea", True, "declaration"),
            ("relevant_dates", "Relevant dates", "متعلقہ تاریخیں", "text", False, "declaration"),
            ("date", "Date of affidavit", "حلف نامے کی تاریخ", "date", True, "declaration"),
            ("place", "Place (notary / oath)", "مقام (نوٹری / حلف)", "text", False, "declaration"),
        ] + WITNESS,
    },
    "undertaking": {
        "sections": [("person", "Person giving undertaking", "اقرار کنندہ"), ("commitment", "Commitment", "اقرار کی تفصیل"), S_WIT],
        "fields": person("person", "person", "Person giving undertaking", "اقرار کنندہ") + [
            ("subject", "Subject", "موضوع", "text", True, "commitment"),
            ("commitment", "Commitment / undertaking", "اقرار / ذمہ داری", "textarea", True, "commitment"),
            ("relevant_dates", "Relevant dates", "متعلقہ تاریخیں", "text", False, "commitment"),
            ("conditions", "Additional conditions", "اضافی شرائط", "textarea", False, "commitment"),
            ("date", "Date", "تاریخ", "date", True, "commitment"),
        ] + WITNESS,
    },
    "authority_letter": {
        "sections": [("principal", "Principal / grantor", "مختار دہندہ"), ("agent", "Authorized person", "مختار (نامزد شخص)"),
                     ("scope", "Authority", "اختیارات"), S_WIT],
        "fields": person("principal", "principal", "Principal", "مختار دہندہ") + person("agent", "agent", "Authorized person", "مختار") + [
            ("purpose", "Purpose of authorization", "اختیار دینے کا مقصد", "text", True, "scope"),
            ("scope", "Scope of authority", "اختیارات کی تفصیل", "textarea", True, "scope"),
            ("duration", "Duration (if applicable)", "مدت (اگر ہو)", "text", False, "scope"),
            ("date", "Date", "تاریخ", "date", True, "scope"),
        ] + WITNESS,
    },
}


def form_spec(doc_type):
    d = DEFS[doc_type]
    return {
        "document_type": doc_type,
        "sections": [{"id": i, "en": e, "ur": u} for i, e, u in d["sections"]],
        "fields": [{"key": k, "en": e, "ur": u, "type": t, "required": r, "section": s} for k, e, u, t, r, s in d["fields"]],
    }
