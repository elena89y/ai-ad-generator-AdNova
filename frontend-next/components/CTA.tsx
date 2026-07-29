import { ArrowRight } from "lucide-react";
import Reveal from "./Reveal";

export default function CTA() {
  return (
    <section id="cta" className="relative mx-auto max-w-6xl px-6 pb-28">
      <Reveal>
        <div className="noise relative overflow-hidden rounded-[2.5rem] border border-border bg-gradient-to-br from-white/[0.06] to-transparent px-8 py-20 text-center sm:px-16">
          <div className="pointer-events-none absolute -top-32 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-accent/20 blur-3xl" />
          <h2 className="relative text-3xl font-semibold tracking-tight sm:text-5xl">
            지금 상품 사진을 올리고
            <br />
            <span className="text-gradient">첫 광고를 만들어보세요</span>
          </h2>
          <p className="relative mx-auto mt-5 max-w-md text-muted">
            구글 · 카카오 · 네이버 계정으로 3초 만에 가입하고, 무료 크레딧
            3개로 바로 시작하세요.
          </p>
          <div className="relative mt-9 flex flex-wrap items-center justify-center gap-4">
            <a
              href="/signup"
              className="group flex items-center gap-2 rounded-full accent-gradient px-7 py-3.5 text-sm font-semibold text-white transition-transform hover:scale-[1.03]"
            >
              무료로 시작하기
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </a>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
