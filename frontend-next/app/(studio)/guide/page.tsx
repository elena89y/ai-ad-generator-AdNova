import Link from "next/link";
import {
  ArrowRight,
  Check,
  ImagePlus,
  Palette,
  Share2,
  Sparkles,
} from "lucide-react";
import Footer from "@/components/Footer";
import Navbar from "@/components/Navbar";

const steps = [
  {
    icon: ImagePlus,
    number: "01",
    title: "상품 사진 준비하기",
    body: "상품이 화면 중앙에 크게 보이고 초점이 맞은 사진을 준비해 주세요. JPG, PNG, WEBP 형식을 사용할 수 있습니다.",
    points: ["상품이 잘 보이는 밝은 사진", "복잡한 배경도 그대로 업로드 가능", "한 번에 한 장씩 업로드"],
  },
  {
    icon: Palette,
    number: "02",
    title: "스타일과 용도 선택하기",
    body: "상품명과 설명을 입력한 뒤 원하는 스타일을 고릅니다. SNS, 카드뉴스, 배너 등 광고를 사용할 용도도 함께 선택할 수 있습니다.",
    points: ["AI 추천 스타일 확인", "원하는 분위기를 직접 선택", "광고 목적에 맞는 비율 설정"],
  },
  {
    icon: Sparkles,
    number: "03",
    title: "광고 생성하기",
    body: "AI가 상품의 형태와 특징을 살리면서 배경, 조명, 분위기를 새롭게 구성합니다. 어울리는 광고 문구도 함께 생성됩니다.",
    points: ["상품의 핵심 특징 보존", "스타일에 맞는 배경과 조명 적용", "헤드라인과 설명 문구 자동 생성"],
  },
  {
    icon: Share2,
    number: "04",
    title: "확인하고 공유하기",
    body: "완성된 광고는 내 광고에서 다시 확인할 수 있습니다. 문구와 이미지를 살펴본 뒤 SNS 공유·내보내기로 바로 사용할 수 있습니다.",
    points: ["생성 결과와 문구 함께 확인", "광고 이미지 다운로드", "SNS용 결과 공유"],
  },
];

export default function GuidePage() {
  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-32">
        <section className="mx-auto max-w-6xl px-6 pb-20">
          <div className="max-w-3xl">
            <p className="text-sm font-medium text-accent">이용 가이드</p>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
              상품 사진 한 장으로
              <br />
              광고를 완성해 보세요
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-muted">
              업로드부터 공유까지, AdNova를 처음 사용하는 분도 네 단계로 쉽게
              광고를 만들 수 있습니다.
            </p>
          </div>

          <div className="mt-16 grid gap-5 md:grid-cols-2">
            {steps.map((step) => {
              const Icon = step.icon;
              return (
                <article
                  key={step.number}
                  className="rounded-3xl border border-border bg-surface p-7"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/5 text-accent-deep">
                      <Icon className="h-5 w-5" />
                    </div>
                    <span className="font-display text-sm text-muted">{step.number}</span>
                  </div>
                  <h2 className="mt-6 text-xl font-semibold">{step.title}</h2>
                  <p className="mt-3 text-sm leading-6 text-muted">{step.body}</p>
                  <ul className="mt-5 space-y-2 text-sm text-soft">
                    {step.points.map((point) => (
                      <li key={point} className="flex items-start gap-2">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              );
            })}
          </div>
        </section>

        <section className="border-y border-border bg-surface/40">
          <div className="mx-auto flex max-w-6xl flex-col gap-5 px-6 py-12 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-semibold">바로 광고를 만들어 볼까요?</h2>
              <p className="mt-2 text-sm text-muted">무료 가입 후 광고 생성 3회를 바로 사용할 수 있습니다.</p>
            </div>
            <Link
              href="/signup"
              className="inline-flex items-center justify-center gap-2 rounded-full accent-gradient px-5 py-3 text-sm font-semibold text-white"
            >
              무료로 시작하기
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
