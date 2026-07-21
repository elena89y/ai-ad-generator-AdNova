import Image from "next/image";
import { ArrowRight, Camera, CheckCircle2, Sparkles } from "lucide-react";
import Reveal from "./Reveal";

export default function Showcase() {
  return (
    <section id="showcase" className="relative mx-auto max-w-6xl px-6 py-28">
      <Reveal className="max-w-2xl">
        <p className="text-sm font-medium text-accent">예시</p>
        <h2 className="mt-3 text-3xl font-semibold sm:text-4xl">
          제품은 그대로, 배경만 달라집니다
        </h2>
        <p className="mt-4 max-w-xl leading-7 text-muted">
          평범한 매장 사진을 올리면 제품의 형태는 살리고, 광고에 어울리는
          배경과 문구를 새롭게 구성합니다.
        </p>
      </Reveal>

      <Reveal delay={0.1} className="mt-12">
        <div className="relative overflow-hidden rounded-3xl border border-border bg-surface p-3 shadow-2xl shadow-black/20 sm:p-5">
          <div className="grid gap-10 md:grid-cols-2 md:gap-5">
            <figure className="min-w-0">
              <div className="mb-3 flex items-center justify-between px-1">
                <div className="flex items-center gap-2 text-sm font-medium text-soft">
                  <Camera className="h-4 w-4 text-muted" />
                  원본 사진
                </div>
                <span className="font-display text-xs text-muted">BEFORE</span>
              </div>
              <div className="relative aspect-square overflow-hidden rounded-2xl border border-white/10 bg-black/20">
                <Image
                  src="/app-assets/showcase/original.jpg"
                  alt="카페에서 촬영한 감 디저트와 감 라테 원본 사진"
                  fill
                  sizes="(max-width: 768px) 100vw, 520px"
                  className="object-cover"
                />
                <div className="absolute inset-x-0 bottom-0 bg-black/65 px-4 py-3 text-xs text-white/80 backdrop-blur-sm">
                  매장에서 촬영한 평범한 상품 사진
                </div>
              </div>
            </figure>

            <div className="absolute left-1/2 top-1/2 z-10 hidden h-12 w-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-4 border-surface accent-gradient shadow-xl md:flex">
              <ArrowRight className="h-5 w-5 text-white" />
            </div>

            <div className="absolute left-1/2 top-1/2 z-10 flex h-11 w-11 -translate-x-1/2 -translate-y-1/2 rotate-90 items-center justify-center rounded-full border-4 border-surface accent-gradient shadow-xl md:hidden">
              <ArrowRight className="h-5 w-5 text-white" />
            </div>

            <figure className="min-w-0">
              <div className="mb-3 flex items-center justify-between px-1">
                <div className="flex items-center gap-2 text-sm font-medium text-white">
                  <Sparkles className="h-4 w-4 text-accent-deep" />
                  AdNova 작업 결과
                </div>
                <span className="font-display text-xs text-accent-deep">AFTER</span>
              </div>
              <div className="relative aspect-square overflow-hidden rounded-2xl border border-accent/40 bg-black/20 shadow-lg shadow-accent/10">
                <Image
                  src="/app-assets/showcase/result.png"
                  alt="밝은 배경과 광고 문구가 적용된 감 라테 광고 결과"
                  fill
                  sizes="(max-width: 768px) 100vw, 520px"
                  className="object-cover"
                />
                <div className="absolute inset-x-0 bottom-0 bg-black/65 px-4 py-3 text-xs text-white/80 backdrop-blur-sm">
                  배경·조명·광고 문구를 적용한 결과
                </div>
              </div>
            </figure>
          </div>

          <div className="mt-5 flex flex-col gap-3 border-t border-border px-1 pt-5 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
            <p>사진 한 장으로 광고에 바로 쓸 수 있는 장면을 만듭니다.</p>
            <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-soft">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-ok" /> 제품 특징 유지
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-ok" /> 배경 재구성
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-ok" /> 문구 생성
              </span>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
