import {
  History,
  Palette,
  RefreshCw,
  Share2,
  Sparkles,
  Wand2,
} from "lucide-react";
import Reveal from "./Reveal";

const features = [
  {
    icon: Wand2,
    title: "제품은 그대로, 배경만 새롭게",
    desc: "AI 인페인팅 기술로 상품은 원본 그대로 보존하고 배경·조명·무드만 광고에 어울리게 교체합니다.",
    span: "md:col-span-2",
  },
  {
    icon: Sparkles,
    title: "AI 카피라이팅",
    desc: "완성된 광고 이미지를 분석해 어울리는 광고 문구를 자동으로 작성합니다.",
    span: "md:col-span-1",
  },
  {
    icon: Palette,
    title: "6가지 스타일 프리셋",
    desc: "모노톤, 웜빈티지, 팝, 에디토리얼, 리얼리즘, 파스텔 플로팅.",
    span: "md:col-span-1",
  },
  {
    icon: RefreshCw,
    title: "AI 스타일 추천 & 재생성",
    desc: "AI가 상품에 어울리는 스타일을 추천하고, 마음에 들 때까지 다시 만들 수 있어요.",
    span: "md:col-span-1",
  },
  {
    icon: History,
    title: "히스토리 관리",
    desc: "지금까지 만든 광고를 한곳에서 관리하고 다시 불러오세요.",
    span: "md:col-span-1",
  },
  {
    icon: Share2,
    title: "채널별 용도 최적화",
    desc: "SNS, 카드뉴스, 배너, 상세페이지, 전단지 — 용도에 맞게 내보내기.",
    span: "md:col-span-2",
  },
];

export default function Features() {
  return (
    <section id="features" className="relative mx-auto max-w-6xl px-6 py-28">
      <Reveal className="max-w-2xl">
        <p className="text-sm font-medium text-accent">기능</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          광고 제작에 필요한 모든 것,
          <br />
          하나의 플랫폼에서
        </h2>
      </Reveal>

      <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-3">
        {features.map((f, i) => (
          <Reveal key={f.title} delay={i * 0.06} className={f.span}>
            <div className="group h-full rounded-3xl border border-border bg-surface p-7 transition-colors hover:border-white/20">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl accent-gradient">
                <f.icon className="h-5 w-5 text-white" strokeWidth={2.2} />
              </div>
              <h3 className="mt-5 text-lg font-medium">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                {f.desc}
              </p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
