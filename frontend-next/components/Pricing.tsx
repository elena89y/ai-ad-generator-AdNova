import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import Reveal from "./Reveal";

const plans = [
  {
    name: "Free",
    price: "₩0",
    desc: "가볍게 체험해보고 싶다면",
    features: [
      "가입 즉시 무료 크레딧 3개",
      "6가지 스타일 프리셋 사용",
      "AI 스타일 추천",
      "생성 히스토리 저장",
    ],
    highlight: false,
  },
  {
    name: "Premium",
    price: "₩9,900",
    period: "/월",
    desc: "본격적으로 판매를 시작한 셀러에게",
    features: [
      "광고 생성 크레딧 무제한",
      "광고 재생성 무제한",
      "SNS 공유용 내보내기",
      "우선 생성 처리",
    ],
    highlight: true,
  },
];

export default function Pricing() {
  return (
    <section id="pricing" className="relative mx-auto max-w-6xl px-6 py-28">
      <Reveal className="max-w-2xl">
        <p className="text-sm font-medium text-accent">요금</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          부담 없이 시작하세요
        </h2>
        <p className="mt-4 text-muted">
          무료 크레딧으로 먼저 써보고, 필요할 때 업그레이드하면 됩니다.
        </p>
      </Reveal>

      <div className="mx-auto mt-14 grid max-w-3xl grid-cols-1 gap-6 md:grid-cols-2">
        {plans.map((p, i) => (
          <Reveal key={p.name} delay={i * 0.08}>
            <div
              className={cn(
                "flex h-full flex-col rounded-3xl border p-8",
                p.highlight
                  ? "border-accent/50 bg-gradient-to-b from-accent/10 to-transparent"
                  : "border-border bg-surface"
              )}
            >
              {p.highlight && (
                <span className="mb-4 w-fit rounded-full accent-gradient px-3 py-1 text-xs font-semibold text-white">
                  ✦ 추천
                </span>
              )}
              <h3 className="text-lg font-medium">{p.name}</h3>
              <p className="mt-1 text-sm text-muted">{p.desc}</p>
              <div className="mt-6 flex items-baseline gap-1">
                <span className="text-3xl font-semibold">{p.price}</span>
                {p.period && (
                  <span className="text-sm text-muted">{p.period}</span>
                )}
              </div>
              <ul className="mt-6 flex flex-1 flex-col gap-3">
                {p.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-white/80">
                    <Check className="h-4 w-4 shrink-0 text-ok" />
                    {f}
                  </li>
                ))}
              </ul>
              <a
                href="/signup"
                className={cn(
                  "mt-8 rounded-full px-5 py-3 text-center text-sm font-medium transition-transform hover:scale-[1.02]",
                  p.highlight
                    ? "accent-gradient text-white"
                    : "border border-border text-foreground hover:bg-white/5"
                )}
              >
                {p.highlight ? "프리미엄 시작하기" : "무료로 시작하기"}
              </a>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
