import { ArrowRight, ImageIcon, Sparkle } from "lucide-react";
import Reveal from "./Reveal";

const examples = [
  { label: "모노톤", from: "from-zinc-500/60 to-zinc-900" },
  { label: "웜빈티지", from: "from-amber-600/50 to-stone-900" },
  { label: "팝", from: "from-fuchsia-600/60 to-indigo-900" },
];

export default function Showcase() {
  return (
    <section id="showcase" className="relative mx-auto max-w-6xl px-6 py-28">
      <Reveal className="max-w-2xl">
        <p className="text-sm font-medium text-accent">예시</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          제품은 그대로, 배경만 달라집니다
        </h2>
        <p className="mt-4 text-muted">
          6가지 스타일 프리셋 중 3가지 예시입니다. 상품은 원본 그대로
          보존되고, 배경과 조명·무드만 스타일에 맞게 새로 생성됩니다.
        </p>
      </Reveal>

      <Reveal delay={0.1} className="mt-14">
        <div className="grid grid-cols-1 items-center gap-6 md:grid-cols-[1fr_auto_1.4fr]">
          <div className="rounded-3xl border border-border bg-surface p-6">
            <div className="flex items-center gap-2 text-xs text-muted">
              <ImageIcon className="h-3.5 w-3.5" />
              원본 상품 사진
            </div>
            <div className="mt-4 flex aspect-square items-center justify-center rounded-2xl border border-dashed border-white/15 bg-white/5">
              <ImageIcon className="h-10 w-10 text-white/25" />
            </div>
          </div>

          <div className="flex justify-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-full accent-gradient rotate-90 md:rotate-0">
              <ArrowRight className="h-5 w-5 text-white" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            {examples.map((ex) => (
              <div
                key={ex.label}
                className="overflow-hidden rounded-2xl border border-border"
              >
                <div
                  className={`relative flex aspect-[3/4] items-center justify-center bg-gradient-to-br ${ex.from}`}
                >
                  <Sparkle className="h-6 w-6 text-white/70" />
                  <div className="absolute inset-x-0 bottom-0 bg-black/40 px-3 py-2 text-center text-xs text-white/90 backdrop-blur">
                    {ex.label}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Reveal>
    </section>
  );
}
