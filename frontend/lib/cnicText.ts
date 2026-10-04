// User-facing text for the CNIC flow. The backend sends English messages; in an Urdu document the form must not show English,
// so known messages are mapped here (no AI call). Unknown messages fall back to what the backend sent.
export const RATE_LIMIT = {
  en: "AI extraction is temporarily rate-limited. Please wait a moment and try again, or enter the information manually.",
  ur: "اے آئی کے ذریعے معلومات حاصل کرنے کی حد عارضی طور پر پوری ہو گئی ہے۔ براہ کرم کچھ دیر انتظار کر کے دوبارہ کوشش کریں، یا معلومات خود درج کریں۔",
};
const UR: Record<string, string> = {
  "Could not confidently extract some information from the CNIC. Please review the highlighted fields or enter them manually.": "شناختی کارڈ سے کچھ معلومات یقین سے حاصل نہیں ہو سکیں۔ براہ کرم نمایاں خانوں کی جانچ کریں یا خود درج کریں۔",
  "We couldn't read the CNIC right now. Please try again, upload clearer images, or enter the information manually.": "ابھی شناختی کارڈ پڑھا نہیں جا سکا۔ براہ کرم دوبارہ کوشش کریں، واضح تصاویر اپ لوڈ کریں یا معلومات خود درج کریں۔",
  "Could not confidently read the CNIC. Please upload clearer images or enter the information manually.": "شناختی کارڈ یقین سے پڑھا نہیں جا سکا۔ براہ کرم واضح تصاویر اپ لوڈ کریں یا معلومات خود درج کریں۔",
  "Please upload the front side of the CNIC.": "براہ کرم شناختی کارڈ کا سامنے والا رخ اپ لوڈ کریں۔",
  "Please upload the back side of the CNIC.": "براہ کرم شناختی کارڈ کا پچھلا رخ اپ لوڈ کریں۔",
  "Please upload a JPG, JPEG, PNG, or WebP image under 10 MB.": "براہ کرم 10 MB سے کم سائز کی JPG، JPEG، PNG یا WebP تصویر اپ لوڈ کریں۔",
  "Please verify CNIC number": "براہ کرم شناختی کارڈ نمبر کی تصدیق کریں",
  "The date of birth could not be read reliably - please enter it manually.": "تاریخ پیدائش یقین سے نہیں پڑھی جا سکی — براہ کرم خود درج کریں۔",
  "Groq is temporarily rate-limited. Please wait a moment and try again.": RATE_LIMIT.ur,
};
export const localizeMsg = (m: string, ur: boolean) => (ur ? UR[m] ?? m : m);
export const rateLimitMsg = (ur: boolean) => (ur ? RATE_LIMIT.ur : RATE_LIMIT.en);
