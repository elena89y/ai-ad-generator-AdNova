import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  Download,
  ImagePlus,
  LogIn,
  MousePointerClick,
  Palette,
  Share2,
  Sparkles,
} from "lucide-react";
import Footer from "@/components/Footer";
import Navbar from "@/components/Navbar";

const overview = [
  { number: "01", label: "로그인" },
  { number: "02", label: "사진과 정보 입력" },
  { number: "03", label: "스타일·용도 선택" },
  { number: "04", label: "생성·공유" },
];

const styles = ["리얼리즘", "에디토리얼", "팝 비비드", "웜 빈티지", "모노톤", "파스텔"];
const purposes = ["SNS", "카드뉴스", "배너", "상세페이지"];

export default function GuidePage() {
  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-28">
        <section className="mx-auto max-w-6xl px-6 pb-24 pt-8">
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-sm font-medium text-accent">이용 가이드</p>
            <h1 className="mt-4 text-4xl font-semibold sm:text-5xl">
              처음이어도 괜찮아요.
              <br />
              사진 한 장부터 같이 시작해요
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-muted">
              로그인부터 광고 저장까지 실제 화면 순서대로 정리했습니다. 아래 네
              단계만 따라 하면 첫 광고를 완성할 수 있습니다.
            </p>
          </div>

          <figure className="mt-12 overflow-hidden rounded-3xl border border-border bg-surface shadow-2xl shadow-black/25">
            <div className="flex h-11 items-center gap-2 border-b border-border px-4">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-300/80" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
              <span className="ml-3 truncate rounded-md bg-background/60 px-3 py-1 text-[11px] text-muted">
                adnova.iridescentseraphim.org
              </span>
            </div>
            <div className="relative aspect-[16/8] min-h-56 bg-background sm:min-h-0">
              <Image
                src="/guide-assets/landing.png"
                alt="실제 AdNova 서비스 첫 화면"
                fill
                priority
                sizes="(max-width: 1200px) 100vw, 1152px"
                className="object-cover object-top"
              />
            </div>
            <figcaption className="border-t border-border px-5 py-3 text-xs text-muted">
              실제 AdNova 첫 화면 · 오른쪽 위의 로그인 또는 무료로 시작하기를 선택하세요.
            </figcaption>
          </figure>

          <ol className="mt-10 grid grid-cols-2 border-y border-border sm:grid-cols-4">
            {overview.map((item, index) => (
              <li
                key={item.number}
                className={`flex items-center gap-3 px-3 py-5 sm:px-5 ${
                  index < overview.length - 1 ? "sm:border-r sm:border-border" : ""
                }`}
              >
                <span className="font-display text-xs text-accent-deep">{item.number}</span>
                <span className="text-sm font-medium text-soft">{item.label}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-y border-border bg-surface/25">
          <div className="mx-auto max-w-6xl px-6">
            <article className="grid items-center gap-10 border-b border-border py-20 lg:grid-cols-2 lg:gap-16">
              <div>
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full accent-gradient font-display text-sm font-bold text-white">
                    01
                  </span>
                  <LogIn className="h-5 w-5 text-accent-deep" />
                </div>
                <h2 className="mt-6 text-2xl font-semibold sm:text-3xl">로그인하고 광고 만들기로 이동하세요</h2>
                <p className="mt-4 leading-7 text-muted">
                  첫 화면 오른쪽 위의 <strong className="font-medium text-soft">무료로 시작하기</strong>를
                  누르면 회원가입 화면으로 이동합니다. 이미 가입했다면 로그인을 선택하세요.
                </p>
                <ol className="mt-6 space-y-4 text-sm leading-6 text-soft">
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    회원가입 때 만든 아이디와 비밀번호로 로그인합니다.
                  </li>
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    Google·Kakao·Naver 버튼으로 소셜 로그인을 사용할 수도 있습니다.
                  </li>
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    로그인이 완료되면 광고 만들기 화면으로 이동합니다.
                  </li>
                </ol>
              </div>

              <figure className="overflow-hidden rounded-2xl border border-border bg-background shadow-xl shadow-black/20">
                <div className="relative aspect-[4/3] sm:aspect-[16/10]">
                  <Image
                    src="/guide-assets/login.png"
                    alt="AdNova 실제 로그인 화면"
                    fill
                    sizes="(max-width: 1024px) 100vw, 540px"
                    className="object-cover object-center"
                  />
                </div>
                <figcaption className="border-t border-border px-4 py-3 text-xs text-muted">
                  실제 로그인 화면 · 아이디와 비밀번호를 입력한 뒤 로그인 버튼을 누르세요.
                </figcaption>
              </figure>
            </article>

            <article className="grid items-center gap-10 border-b border-border py-20 lg:grid-cols-2 lg:gap-16">
              <figure className="order-2 overflow-hidden rounded-2xl border border-border bg-background shadow-xl shadow-black/20 lg:order-1">
                <div className="relative aspect-[4/3]">
                  <Image
                    src="/app-assets/showcase/original.jpg"
                    alt="광고 제작에 사용할 감 디저트와 감 라테 원본 사진"
                    fill
                    sizes="(max-width: 1024px) 100vw, 540px"
                    className="object-cover"
                  />
                  <span className="absolute left-4 top-4 rounded-full bg-black/65 px-3 py-1.5 text-xs font-medium text-white backdrop-blur-sm">
                    업로드할 원본 사진 예시
                  </span>
                </div>
                <figcaption className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-4 py-3 text-xs text-muted">
                  <span>JPG · PNG · WEBP</span>
                  <span>최대 15MB</span>
                  <span>상품이 선명한 사진 권장</span>
                </figcaption>
              </figure>

              <div className="order-1 lg:order-2">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full accent-gradient font-display text-sm font-bold text-white">
                    02
                  </span>
                  <ImagePlus className="h-5 w-5 text-accent-deep" />
                </div>
                <h2 className="mt-6 text-2xl font-semibold sm:text-3xl">사진을 올리고 상품 정보를 적어주세요</h2>
                <p className="mt-4 leading-7 text-muted">
                  광고 만들기 화면 왼쪽의 <strong className="font-medium text-soft">제품 사진 업로드</strong>를
                  눌러 사진을 고릅니다. 상품명은 필수이고, 추가 요청은 원하는 경우에만 적으면 됩니다.
                </p>
                <ol className="mt-6 space-y-4 text-sm leading-6 text-soft">
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    제품 전체가 잘 보이고 초점이 맞은 사진을 선택하세요.
                  </li>
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    상품명에는 고객에게 보여줄 실제 제품 이름을 입력하세요.
                  </li>
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    추가 요청에는 “여름 느낌”, “고급스럽게”처럼 원하는 분위기를 적을 수 있습니다.
                  </li>
                </ol>
                <div className="mt-7 border-l-2 border-accent pl-4 text-sm leading-6 text-muted">
                  배경이 복잡해도 업로드할 수 있지만, 상품이 가려지지 않은 사진일수록 결과가 안정적입니다.
                </div>
              </div>
            </article>

            <article className="grid items-center gap-10 border-b border-border py-20 lg:grid-cols-2 lg:gap-16">
              <div>
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full accent-gradient font-display text-sm font-bold text-white">
                    03
                  </span>
                  <Palette className="h-5 w-5 text-accent-deep" />
                </div>
                <h2 className="mt-6 text-2xl font-semibold sm:text-3xl">스타일과 사용할 용도를 고르세요</h2>
                <p className="mt-4 leading-7 text-muted">
                  스타일은 광고의 배경·조명·분위기를 정합니다. 용도는 결과를 사용할 채널에 맞게 구성하는 항목입니다.
                </p>
                <ol className="mt-6 space-y-4 text-sm leading-6 text-soft">
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    여섯 가지 스타일 중 제품과 가장 잘 어울리는 하나를 선택합니다.
                  </li>
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    SNS·카드뉴스·배너·상세페이지 중 실제 사용할 용도를 고릅니다.
                  </li>
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    선택을 확인한 뒤 아래의 광고 생성 버튼을 한 번만 누르세요.
                  </li>
                </ol>
              </div>

              <div className="rounded-2xl border border-border bg-background/75 p-5 shadow-xl shadow-black/20 sm:p-7">
                <div className="flex items-center justify-between border-b border-border pb-4">
                  <div>
                    <p className="text-xs text-muted">광고 만들기</p>
                    <p className="mt-1 text-sm font-semibold">스타일과 용도 선택</p>
                  </div>
                  <MousePointerClick className="h-5 w-5 text-accent-deep" />
                </div>
                <div className="mt-6">
                  <p className="text-xs font-medium text-muted">02 · 스타일</p>
                  <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {styles.map((style, index) => (
                      <span
                        key={style}
                        className={`rounded-lg border px-3 py-2 text-center text-xs ${
                          index === 0
                            ? "border-accent bg-accent/20 text-white"
                            : "border-border bg-surface/60 text-muted"
                        }`}
                      >
                        {style}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="mt-6">
                  <p className="text-xs font-medium text-muted">03 · 용도</p>
                  <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {purposes.map((purpose, index) => (
                      <span
                        key={purpose}
                        className={`rounded-lg border px-2 py-2 text-center text-xs ${
                          index === 0
                            ? "border-accent bg-accent/20 text-white"
                            : "border-border bg-surface/60 text-muted"
                        }`}
                      >
                        {purpose}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="mt-6 flex items-center justify-center gap-2 rounded-xl accent-gradient px-4 py-3 text-sm font-semibold text-white">
                  <Sparkles className="h-4 w-4" /> 광고 생성
                </div>
              </div>
            </article>

            <article className="grid items-center gap-10 py-20 lg:grid-cols-2 lg:gap-16">
              <figure className="order-2 overflow-hidden rounded-2xl border border-accent/30 bg-background shadow-xl shadow-accent/10 lg:order-1">
                <div className="relative aspect-square">
                  <Image
                    src="/app-assets/showcase/result.png"
                    alt="AdNova로 만든 감 라테 광고 결과"
                    fill
                    sizes="(max-width: 1024px) 100vw, 540px"
                    className="object-cover"
                  />
                </div>
                <div className="grid grid-cols-3 border-t border-border text-xs">
                  <span className="flex items-center justify-center gap-1.5 border-r border-border px-2 py-3 text-soft">
                    <Download className="h-3.5 w-3.5" /> 다운로드
                  </span>
                  <span className="flex items-center justify-center gap-1.5 border-r border-border px-2 py-3 text-soft">
                    <Share2 className="h-3.5 w-3.5" /> 공유
                  </span>
                  <span className="flex items-center justify-center gap-1.5 px-2 py-3 text-soft">
                    <Sparkles className="h-3.5 w-3.5" /> 다시 생성
                  </span>
                </div>
              </figure>

              <div className="order-1 lg:order-2">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full accent-gradient font-display text-sm font-bold text-white">
                    04
                  </span>
                  <Share2 className="h-5 w-5 text-accent-deep" />
                </div>
                <h2 className="mt-6 text-2xl font-semibold sm:text-3xl">결과를 확인하고 저장하거나 공유하세요</h2>
                <p className="mt-4 leading-7 text-muted">
                  생성이 끝나면 광고 이미지와 문구가 함께 표시됩니다. 결과가 마음에 들면 다운로드하거나 SNS 공유 화면으로 이동할 수 있습니다.
                </p>
                <ol className="mt-6 space-y-4 text-sm leading-6 text-soft">
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    생성 직후에는 같은 입력 사진으로 다시 생성할 수 있습니다.
                  </li>
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    다운로드를 누르면 완성된 이미지를 기기에 저장합니다.
                  </li>
                  <li className="flex gap-3">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-ok" />
                    이전 결과는 내 광고에서 확인하고 공유하거나 삭제할 수 있습니다.
                  </li>
                </ol>
                <div className="mt-7 border-l-2 border-accent pl-4 text-sm leading-6 text-muted">
                  생성이 진행되는 동안에는 페이지를 닫지 말고 완료 안내가 나타날 때까지 기다려 주세요.
                </div>
              </div>
            </article>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-24">
          <div className="grid gap-10 lg:grid-cols-[0.75fr_1.25fr]">
            <div>
              <p className="text-sm font-medium text-accent">문제가 생겼나요?</p>
              <h2 className="mt-3 text-2xl font-semibold sm:text-3xl">먼저 이것부터 확인해 보세요</h2>
              <p className="mt-4 text-sm leading-6 text-muted">
                아래 방법으로 해결되지 않으면 고객센터에서 1:1 문의를 남겨 주세요.
              </p>
            </div>
            <dl className="divide-y divide-border border-y border-border">
              <div className="grid gap-2 py-5 sm:grid-cols-[10rem_1fr]">
                <dt className="text-sm font-medium text-soft">사진이 올라가지 않아요</dt>
                <dd className="text-sm leading-6 text-muted">로그인 상태와 파일 형식, 15MB 이하인지 확인하세요.</dd>
              </div>
              <div className="grid gap-2 py-5 sm:grid-cols-[10rem_1fr]">
                <dt className="text-sm font-medium text-soft">생성 버튼이 안 눌려요</dt>
                <dd className="text-sm leading-6 text-muted">사진 업로드와 상품명 입력이 완료됐는지 확인하세요.</dd>
              </div>
              <div className="grid gap-2 py-5 sm:grid-cols-[10rem_1fr]">
                <dt className="text-sm font-medium text-soft">결과를 다시 보고 싶어요</dt>
                <dd className="text-sm leading-6 text-muted">상단 메뉴의 내 광고에서 지금까지 만든 결과를 확인하세요.</dd>
              </div>
            </dl>
          </div>

          <div className="mt-16 flex flex-col gap-5 border-t border-border pt-10 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-semibold">이제 첫 광고를 만들어 볼까요?</h2>
              <p className="mt-2 text-sm text-muted">무료 가입 후 제공되는 크레딧으로 바로 시작할 수 있습니다.</p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Link
                href="/support"
                className="inline-flex items-center justify-center rounded-full border border-border px-5 py-3 text-sm font-semibold text-soft transition-colors hover:border-white/30 hover:text-white"
              >
                고객센터 보기
              </Link>
              <Link
                href="/signup"
                className="inline-flex items-center justify-center gap-2 rounded-full accent-gradient px-5 py-3 text-sm font-semibold text-white"
              >
                무료로 시작하기
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
