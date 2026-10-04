"""Run: cd backend && python -m unittest discover tests -v   (no network, no API keys needed)"""
import json, unittest
from app.services import cnic as C, cnic_vision as V
from app.services.cnic import normalize_cnic, validate_cnic
from app.pdf.builder import Writer

CUR, PERM = "مکان نمبر 18، گلی نمبر 7، فرید ٹاؤن، جہلم، پنجاب", "گاؤں ایبیسی، تحصیل ایکس وائی زیڈ، ضلع جہلم"
RAW = dict(full_name="محمد احمد خان", father_or_husband_name="عبدالرحمن خان", cnic_number="35202-9876543-0", date_of_birth="12.04.1998",
           gender="M", current_address=CUR, permanent_address=PERM)


def check(**over):
    return V.validate_extracted(V.CNICExtractedData.model_validate({**RAW, **over}))


class Normalize(unittest.TestCase):
    def test1_english(self): self.assertEqual(normalize_cnic("35202-9876543-0"), "35202-9876543-0")
    def test2_reversed(self): self.assertEqual(normalize_cnic("0-9876543-35202"), "35202-9876543-0")
    def test3_reversed_other(self): self.assertEqual(normalize_cnic("7-2468135-35202"), "35202-2468135-7")
    def test4_not_reversed_twice(self): self.assertEqual(normalize_cnic("35202-2468135-7"), "35202-2468135-7")
    def test5_invalid(self): self.assertIsNone(normalize_cnic("1234-5678"))
    def test_digits_inside_groups_untouched(self): self.assertEqual(normalize_cnic("0-9876543-35202").split("-")[1], "9876543")
    def test_ocr_noise(self):
        self.assertEqual(normalize_cnic(" 35202 – 9876543 — 0 "), "35202-9876543-0")
        self.assertEqual(normalize_cnic("٣٥٢٠٢-٩٨٧٦٥٤٣-٠"), "35202-9876543-0")  # Arabic-Indic digits
        self.assertEqual(normalize_cnic("\u200e0\u200e-9876543-35202"), "35202-9876543-0")
    def test_ambiguous_returns_none(self):
        self.assertIsNone(normalize_cnic("3520298765430"))             # unseparated: group order unknowable
        self.assertIsNone(normalize_cnic("35202-9876543-05"))          # wrong group length
        self.assertIsNone(normalize_cnic("35202-9876543-0 and 35201-1111111-1"))  # two different numbers
        self.assertIsNone(normalize_cnic("85202-9876543-0"))           # province digit outside 1-7
    def test_validate(self):
        self.assertTrue(validate_cnic("35202-9876543-0")); self.assertFalse(validate_cnic("0-9876543-35202"))


BACK_UR = "موجودہ پتہ:\nمکان 25 گلی 4 گلشن کالونی جہلم پنجاب\nمستقل پتہ:\nگاؤں ایبیسی تحصیل ایکس وائی زیڈ ضلع جہلم\nRegistration Centre\nJHELUM"
ADDR_A, ADDR_B = "مکان 25 گلی 4 گلشن کالونی جہلم پنجاب", "گاؤں ایبیسی تحصیل ایکس وائی زیڈ ضلع جہلم"


class VisionValidation(unittest.TestCase):
    def test_clean_read_keeps_urdu_and_keeps_addresses_separate(self):  # TESTS 1-4, 10
        f, conf, w = check()
        self.assertEqual((f["name"], f["father_or_husband_name"]), ("محمد احمد خان", "عبدالرحمن خان"))
        self.assertEqual((f["current_address"], f["permanent_address"]), (CUR, PERM))
        self.assertEqual((f["cnic"], f["date_of_birth"], f["gender"]), ("35202-9876543-0", "12-04-1998", "Male")); self.assertEqual(w, [])

    def test5_rtl_visual_order_is_normalized_by_group_not_by_digit(self):
        self.assertEqual(check(cnic_number="0-9876543-35202")[0]["cnic"], "35202-9876543-0")
        self.assertEqual(check(cnic_number="۰-۹۸۷۶۵۴۳-۳۵۲۰۲")[0]["cnic"], "35202-9876543-0")  # Urdu digits
        self.assertEqual(check(cnic_number="\u202b0-9876543-35202\u202c")[0]["cnic"], "35202-9876543-0")

    def test_model_cnic_is_never_trusted(self):
        for bad in ("35202987654300", "1234-5678", "35202-9876543", "99999-9876543-0", "35202-9876543-0 / 35201-1111111-1"):
            f, _, w = check(cnic_number=bad); self.assertIsNone(f["cnic"], bad); self.assertIn(V.VERIFY_CNIC, w)
        self.assertEqual(check(cnic_number=None)[2], [])  # simply not detected: no 'verify' noise

    def test11_unreadable_fields_are_null(self):
        f, conf, _ = check(permanent_address=None, date_of_birth="null", father_or_husband_name="N/A", gender="")
        self.assertEqual((f["permanent_address"], f["date_of_birth"], f["father_or_husband_name"], f["gender"]), (None,) * 4)
        self.assertIsNone(conf["permanent_address"]); self.assertEqual(f["current_address"], CUR)

    def test_label_only_or_junk_address_is_rejected_not_kept(self):
        for junk in ("موجودہ پتہ", "مستقل پتہ:", "Permanent Address", "123456", "abc", "35202-9876543-0", "محمد احمد خان"):
            self.assertIsNone(check(current_address=junk)[0]["current_address"], junk)

    def test_addresses_are_never_swapped_or_copied(self):
        f = check(current_address=None)[0]; self.assertIsNone(f["current_address"]); self.assertEqual(f["permanent_address"], PERM)
        f, conf, _ = check(permanent_address=CUR); self.assertEqual((f["current_address"], f["permanent_address"]), (CUR, CUR)); self.assertEqual(conf["current_address"], "medium")  # flagged

    def test_bad_dates_and_names(self):
        for d in ("31.02.1990", "99.99.9999", "1990", "12.04.2999"):
            self.assertIsNone(check(date_of_birth=d)[0]["date_of_birth"], d)
        self.assertEqual(check(date_of_birth="۱۲-۰۴-۱۹۹۸")[0]["date_of_birth"], "12-04-1998")
        self.assertIsNone(check(full_name="12345")[0]["name"])

    def test_pydantic_drops_extra_keys_and_non_strings(self):
        d = V.CNICExtractedData.model_validate({**RAW, "full_name": ["x"], "religion": "x", "cnic_number": 12})
        self.assertIsNone(d.full_name); self.assertFalse(hasattr(d, "religion")); self.assertEqual(d.cnic_number, "12")

    def test_parse_model_json_tolerates_fences_and_think_blocks(self):
        raw = json.dumps(RAW, ensure_ascii=False)
        for c in (raw, f"```json\n{raw}\n```", f"<think>hmm</think>\n{raw}", f"Here you go: {raw} done"):
            self.assertEqual(V.parse_model_json(c).cnic_number, "35202-9876543-0")
        for c in ("", "not json", "[1,2]", "{broken"):
            with self.assertRaises(V.VisionError): V.parse_model_json(c)

    def test_request_carries_one_composite_image_with_schema(self):
        p = V._build_payload(b"COMPOSITE", True); parts = p["messages"][0]["content"]
        self.assertEqual([x["type"] for x in parts], ["text", "image_url"])
        self.assertTrue(parts[1]["image_url"]["url"].endswith("Q09NUE9TSVRF"))
        self.assertEqual(p["response_format"]["type"], "json_schema"); self.assertFalse(p["response_format"]["json_schema"]["schema"]["additionalProperties"])
        self.assertEqual(V._build_payload(b"a", False)["response_format"], {"type": "json_object"})
        for needle in ("FRONT SIDE", "BACK SIDE", "موجودہ پتہ", "مستقل پتہ", "35202-9876543-0", "Do not reverse individual digits", "never change it to"):
            self.assertIn(needle, V.PROMPT)


class GroqWire(unittest.IsolatedAsyncioTestCase):
    """The REAL _call_groq code path against a mocked HTTP transport: headers, key, model, one request, schema -> json_object fallback."""
    def setUp(self):
        old = V.settings.GROQ_VISION_API_KEY; V.settings.GROQ_VISION_API_KEY = "vision-key"
        self.addCleanup(setattr, V.settings, "GROQ_VISION_API_KEY", old)
        old_structured = V.settings.GROQ_VISION_STRUCTURED; V.settings.GROQ_VISION_STRUCTURED = True
        self.addCleanup(setattr, V.settings, "GROQ_VISION_STRUCTURED", old_structured)

    def patch(self, handler):
        import httpx
        real = httpx.AsyncClient
        self.addCleanup(setattr, V.httpx, "AsyncClient", real)
        V.httpx.AsyncClient = lambda **kw: real(transport=httpx.MockTransport(handler), **kw)

    async def test_single_request_uses_vision_key_model_and_both_images(self):
        import httpx
        old = V.settings.GROQ_API_KEY; V.settings.GROQ_API_KEY = "doc-key"   # the document-generation key must NOT be used when a vision key is set
        self.addCleanup(setattr, V.settings, "GROQ_API_KEY", old)
        seen = []
        def h(req):
            seen.append(req); return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(RAW, ensure_ascii=False)}}]})
        self.patch(h)
        out = await V._call_groq(b"COMPOSITE")
        self.assertEqual(len(seen), 1); r = seen[0]; body = json.loads(r.content)
        self.assertEqual(r.headers["authorization"], "Bearer vision-key"); self.assertEqual(r.url.host, "api.groq.com")
        self.assertEqual(body["model"], "qwen/qwen3.8-27b"); self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(sum(p["type"] == "image_url" for p in body["messages"][0]["content"]), 1)
        self.assertEqual(V.parse_model_json(out).full_name, "محمد احمد خان")

    async def test_http_400_is_not_retried_with_another_request(self):
        import httpx
        n = []
        def h(req):
            n.append(1); return httpx.Response(400, json={"error": {"code": "x"}})
        self.patch(h)
        with self.assertRaises(V.VisionError): await V._call_groq(b"COMPOSITE")
        self.assertEqual(len(n), 1)

    async def test_429_makes_exactly_one_request_and_raises_RateLimited(self):
        import httpx
        n = []
        def h(req):
            n.append(1); return httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"code": "rate_limit_exceeded"}})
        self.patch(h)
        with self.assertRaises(V.RateLimited) as cm: await V._call_groq(b"COMPOSITE")
        self.assertEqual(len(n), 1); self.assertEqual(cm.exception.retry_after, 7)

    async def test_http_errors_and_timeouts_become_VisionError(self):
        import httpx
        for handler in (lambda r: httpx.Response(401), lambda r: httpx.Response(429), lambda r: httpx.Response(500)):
            self.patch(handler)
            with self.assertRaises(V.VisionError): await V._call_groq(b"COMPOSITE")
        def boom(r): raise httpx.ReadTimeout("t")
        self.patch(boom)
        with self.assertRaises(V.VisionError): await V._call_groq(b"COMPOSITE")


class RtlRendering(unittest.TestCase):
    def test_cnic_and_dates_keep_ltr_order_in_urdu_line(self):
        w = Writer(True, "p")
        for token in ("35202-9876543-0", "05-10-2026"):
            out = w.shape(f"شناختی کارڈ نمبر \u2066{token}\u2069 ساکن جہلم")
            self.assertIn(token, out); self.assertNotIn("\u2066", out)
        self.assertNotIn("0-9876543-35202", w.shape("نمبر 35202-9876543-0 ساکن"))


if __name__ == "__main__":
    unittest.main()



class OneRequestAndPresentation(unittest.IsolatedAsyncioTestCase):
    def test_composite_contains_front_and_back_panels(self):
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(V.prepare_cnic_composite(Image.new("RGB", (1000, 600), (200, 220, 200)), Image.new("RGB", (900, 570), (220, 200, 200)))))
        self.assertEqual(im.format, "JPEG"); self.assertEqual(im.width, 1600); self.assertGreater(im.height, 900)

    def test_composite_is_the_only_image_in_the_request(self):
        parts = V._build_payload(b"COMPOSITE", True)["messages"][0]["content"]
        self.assertEqual([x["type"] for x in parts], ["text", "image_url"])

    def test_no_second_pass_code_left(self):
        for name in ("_retry_addresses", "_call_groq_addresses", "ADDRESS_PROMPT", "_post"):
            self.assertFalse(hasattr(V, name), name)

    async def test_extract_makes_one_groq_call_even_when_addresses_missing(self):
        from PIL import Image
        calls = []
        async def fake(composite):
            calls.append(1); return json.dumps({"full_name": "Sami Naeem", "cnic_number": "37301-4950901-3"})
        old = V._call_groq; V._call_groq = fake
        self.addCleanup(setattr, V, "_call_groq", old)
        r = await V.extract_cnic(Image.new("RGB", (400, 250)), Image.new("RGB", (400, 250)))
        self.assertEqual(len(calls), 1); self.assertIsNone(r["fields"]["current_address"]); self.assertTrue(r["ok"])

    async def test_extract_429_returns_rate_limit_profile_without_looping(self):
        from PIL import Image
        calls = []
        async def fake(composite):
            calls.append(1); raise V.RateLimited(12)
        old = V._call_groq; V._call_groq = fake
        self.addCleanup(setattr, V, "_call_groq", old)
        r = await V.extract_cnic(Image.new("RGB", (400, 250)), Image.new("RGB", (400, 250)))
        self.assertEqual(len(calls), 1)
        self.assertFalse(r["ok"]); self.assertFalse(r["success"]); self.assertEqual(r["error_code"], "GROQ_RATE_LIMIT"); self.assertEqual(r["retry_after"], 12)
        self.assertEqual(r["message"], V.MSG_RATE_LIMIT)

    def test_presentation_preserves_printed_urdu_and_uses_renderings_for_the_other_script(self):
        data = V.CNICExtractedData(full_name="Naeem Tahir", father_or_husband_name="Muhammad Hussain", gender="M",
                                   full_name_ur="نعیم طاہر", full_name_en="WRONG", father_or_husband_name_ur="محمد حسین",
                                   current_address="مکان نمبر 18، گلی نمبر 7، جہلم", current_address_en="House 18, Street 7, Jhelum")
        fields, _, _ = V.validate_extracted(data); pres = V.build_presentation(fields, data)
        self.assertEqual(pres["en"]["name"], "Naeem Tahir"); self.assertEqual(pres["ur"]["name"], "نعیم طاہر")
        self.assertEqual(pres["ur"]["father_or_husband_name"], "محمد حسین")
        self.assertEqual(pres["ur"]["current_address"], "مکان نمبر 18، گلی نمبر 7، جہلم")      # printed Urdu preserved exactly
        self.assertEqual(pres["en"]["current_address"], "House 18, Street 7, Jhelum")
        self.assertEqual((pres["en"]["gender"], pres["ur"]["gender"]), ("Male", "مرد"))
        self.assertIsNone(pres["ur"]["permanent_address"])                                   # missing stays missing

    def test_presentation_rejects_renderings_that_change_numbers_or_script(self):
        data = V.CNICExtractedData(current_address="House 18, Street 7, Jhelum", current_address_ur="مکان نمبر 19، گلی نمبر 7، جہلم",
                                   full_name="Ali Khan", full_name_ur="Ali Khan")
        fields, _, _ = V.validate_extracted(data); pres = V.build_presentation(fields, data)
        self.assertIsNone(pres["ur"]["current_address"])    # house number changed 18 -> 19: dropped, UI falls back to the printed value
        self.assertIsNone(pres["ur"]["name"])               # "Urdu" rendering that is not Urdu script: dropped
