import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = { title: "DraftKar — Document preparation", description: "AI-powered document preparation for Pakistani document writers." };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body>{children}</body></html>);
}
