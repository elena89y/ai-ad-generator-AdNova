import { Download, ImagePlus, Sliders, Sparkles } from "lucide-react";
import Reveal from "./Reveal";

const steps = [
  {
    icon: ImagePlus,
    title: "업로드 & 자동 전처리",
    desc: "상품 사진을 올리면 배경 제거, 리사이즈, 품질 보정까지 자동으로 처리합니다.",
  },
  {
    icon: Sliders,
    title: "스타일 결정",
    desc: "AI가 추천하는 스타일 후보 중에 고르거나, 원하는 무드를 직접 입력하세요.",
  },
  {
    icon: Sparkles,
    title: "AI 광고 이미지 생성",
    desc: "제품은 그대로 살리고 배경만 스타일에 맞게 새로 그려냅니다.",
  },
  {
    icon: Download,
    title: "카피 생성 & 내보내기",
    desc: "이미지에 어울리는 광고 문구까지 완성해 SNS용으로 바로 내보내세요.",
  },
];

export default function HowItWorks() {
  return (
    <section id="how" className="relative border-y border-border bg-surface/40 py-28">
      <div className="mx-auto max-w-6xl px-6">
        <Reveal className="max-w-2xl">
          <p className="text-sm font-medium text-accent">작동 방식</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
            4단계면 충분합니다
          </h2>
        </Reveal>

        <div className="relative mt-16 grid grid-cols-1 gap-10 md:grid-cols-4 md:gap-6">
          <div className="absolute top-6 hidden h-px w-full bg-gradient-to-r from-transparent via-border to-transparent md:block" />
          {steps.map((s, i) => (
            <Reveal key={s.title} delay={i * 0.08} className="relative">
              <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-background text-sm font-medium">
                0{i + 1}
              </div>
              <div className="mt-5 flex h-9 w-9 items-center justify-center rounded-xl bg-white/5">
                <s.icon className="h-4 w-4 text-accent-deep" />
              </div>
              <h3 className="mt-4 text-base font-medium">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                {s.desc}
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
