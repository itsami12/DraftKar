import type { Config } from "tailwindcss";
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: {
    colors: { ink: "#12372A", ink2: "#1C4A39", stamp: "#C8841A", stampsoft: "#F6E9C9", paper: "#FAF8F3", line: "#E4DFD2" },
    fontFamily: { display: ["Georgia", "Cambria", "'Times New Roman'", "serif"], urdu: ["'Noto Nastaliq Urdu'", "'Noto Naskh Arabic'", "'Segoe UI'", "Tahoma", "serif"] },
  } },
  plugins: [],
} satisfies Config;
