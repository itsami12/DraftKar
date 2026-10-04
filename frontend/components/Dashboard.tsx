"use client";
import { Home, Gavel, FileSignature, UserCheck, ArrowRight } from "lucide-react";
import Img from "./Img";
import type { DocMeta } from "@/types";

const VIS: Record<string, { img: string; Icon: any; pos: string }> = {
  rent_agreement: { img: "/images/doc-rent.svg", Icon: Home, pos: "left top" },
  affidavit: { img: "/images/doc-affidavit.svg", Icon: Gavel, pos: "center" },
  undertaking: { img: "/images/doc-undertaking.svg", Icon: FileSignature, pos: "right center" },
  authority_letter: { img: "/images/doc-authority.svg", Icon: UserCheck, pos: "right bottom" },
};

export default function Dashboard({ docs, onSelect }: { docs: DocMeta[]; onSelect: (d: DocMeta) => void }) {
  return (
    <div>
      <h1 className="font-display text-3xl font-bold text-ink md:text-4xl">What document do you want to prepare?</h1>
      <p className="mt-2 text-neutral-600">Choose a document type to get started.</p>
      <div className="mt-8 grid gap-6 sm:grid-cols-2">
        {docs.map((d) => {
          const v = VIS[d.type]; const Icon = v.Icon;
          return (
            <button key={d.type} onClick={() => onSelect(d)} className="group overflow-hidden rounded-2xl border border-line bg-white text-left transition hover:border-ink hover:shadow-md">
              <div className="relative h-40 overflow-hidden bg-stampsoft">
                <div className="absolute inset-0 bg-cover opacity-40" style={{ backgroundImage: "url(/images/stamp-paper.png)", backgroundPosition: v.pos }} />
                <Img src={v.img} alt={`${d.en} illustration`} className="relative mx-auto h-full object-contain py-3" />
              </div>
              <div className="p-5">
                <div className="flex items-center gap-2 text-ink"><Icon size={18} /><h2 className="font-display text-xl font-semibold">{d.en}</h2></div>
                <p dir="rtl" lang="ur" className="mt-1 font-urdu text-lg text-stamp">{d.ur}</p>
                <p className="mt-2 text-sm text-neutral-600">{d.desc}</p>
                <span className="btn btn-primary mt-4">Select <ArrowRight size={16} /></span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
