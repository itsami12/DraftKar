"use client";
import { useState } from "react";
import { FileText } from "lucide-react";
/** Local image with graceful fallback if it fails to load. */
export default function Img({ src, alt, className = "" }: { src: string; alt: string; className?: string }) {
  const [bad, setBad] = useState(false);
  if (bad) return <div className={`flex items-center justify-center bg-stampsoft text-stamp ${className}`}><FileText size={36} aria-label={alt} /></div>;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className={className} onError={() => setBad(true)} />;
}
