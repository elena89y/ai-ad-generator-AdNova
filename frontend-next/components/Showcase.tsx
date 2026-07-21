import Image from "next/image";
import { ArrowRight, ImageIcon, Sparkle } from "lucide-react";
import Reveal from "./Reveal";

export default function Showcase() {
  return (
    <section id="showcase" className="relative mx-auto max-w-6xl px-6 py-28">
      <Reveal className="max-w-2xl">
        <p className="text-sm font-medium text-accent">예시</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          제품은 그대로, 배경만 달라집니다
        </h2>
        <p className="mt-4 text-muted">
          원본 상품은 그대로 보존하고, 배경과 조명·무드만 스타일에 맞게
          새로 생성합니다.
        </p>
      </Reveal>

      <Reveal delay={0.1} className="mt-14">
        <div className="grid grid-cols-1 items-center gap-6 md:grid-cols-[0.8fr_auto_1.4fr]">
          <div className="rounded-3xl border border-border bg-surface p-6">
            <div className="flex items-center gap-2 text-xs text-muted">
              <ImageIcon className="h-3.5 w-3.5" />
              원본 상품 사진
            </div>
            <div className="relative mt-4 aspect-square overflow-hidden rounded-2xl border border-white/10 bg-white">
              <Image
                src="/app-assets/demo-product.jpg"
                alt="배경을 바꾸기 전 원본 밀크티 상품 사진"
                fill
                sizes="(max-width: 768px) 100vw, 280px"
                className="object-contain"
              />
            </div>
          </div>

          <div className="flex justify-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-full accent-gradient rotate-90 md:rotate-0">
              <ArrowRight className="h-5 w-5 text-white" />
            </div>
          </div>

          <div className="rounded-3xl border border-border bg-surface p-6">
            <div className="flex items-center gap-2 text-xs text-muted">
              <Sparkle className="h-3.5 w-3.5 text-accent-deep" />
              작업 결과
            </div>
            <div className="relative mt-4 aspect-[16/10] overflow-hidden rounded-2xl border border-white/10 bg-black/20">
              <Image
                src="/app-assets/demo-ad.jpg"
                alt="배경이 새롭게 생성된 밀크티 광고 결과"
                fill
                sizes="(max-width: 768px) 100vw, 620px"
                className="object-cover"
              />
              <div className="absolute inset-x-0 bottom-0 bg-black/55 px-4 py-3 text-sm font-medium text-white backdrop-blur-sm">
                상품은 그대로, 새로운 배경과 무드
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted">
              <span className="rounded-full border border-border px-3 py-1.5">상품 보존</span>
              <span className="rounded-full border border-border px-3 py-1.5">배경 재구성</span>
              <span className="rounded-full border border-border px-3 py-1.5">광고 문구 생성</span>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
