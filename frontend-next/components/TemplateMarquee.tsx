import Link from "next/link";

import { CATALOG } from "@/lib/catalog";
import Reveal from "./Reveal";

/* 예시 섹션 아래 템플릿 무한 마퀴.
   두 줄이 반대 방향으로 흘러 밀도감을 주고, 각 카드는 스튜디오로 연결. */

function templateHref(t: (typeof CATALOG)[number]): string {
  // 갤러리와 동일하게 템플릿 전용 페이지로 (스튜디오 생성으로 가지 않음)
  return `/templates/${encodeURIComponent(t.id)}`;
}

function Row({
  items,
  reverse = false,
  duration,
}: {
  items: typeof CATALOG;
  reverse?: boolean;
  duration: string;
}) {
  // 리스트를 2번 이어붙여 -50% 이동 시 이음새 없이 무한 반복
  const doubled = [...items, ...items];
  return (
    <div className="marquee-viewport relative overflow-hidden">
      {/* 좌우 페이드 마스크 */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-background to-transparent sm:w-28" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-background to-transparent sm:w-28" />
      <div
        className={`marquee-track flex gap-4 py-2${reverse ? " reverse" : ""}`}
        style={{ ["--marquee-duration" as string]: duration }}
      >
        {doubled.map((t, i) => (
          <Link
            key={`${t.id}-${i}`}
            href={templateHref(t)}
            aria-hidden={i >= items.length}
            tabIndex={i >= items.length ? -1 : 0}
            className="group relative aspect-[3/4] w-40 flex-none overflow-hidden rounded-2xl border border-border bg-surface shadow-lg shadow-black/20 transition sm:w-48 hover:-translate-y-1 hover:border-accent/50"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={t.img}
              alt={t.name}
              loading="lazy"
              className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
            />
            <div className="absolute inset-x-0 bottom-0 translate-y-2 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2.5 pt-8 opacity-0 transition duration-300 group-hover:translate-y-0 group-hover:opacity-100">
              <p className="truncate text-xs font-semibold text-white">{t.name}</p>
              <p className="truncate text-[10px] text-white/70">{t.style_label}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function TemplateMarquee() {
  const mid = Math.ceil(CATALOG.length / 2);
  const rowA = CATALOG.slice(0, mid);
  const rowB = CATALOG.slice(mid);
  return (
    <section className="relative py-24">
      <Reveal className="mx-auto mb-10 max-w-6xl px-6">
        <p className="text-sm font-medium text-accent">템플릿</p>
        <h2 className="mt-3 text-3xl font-semibold sm:text-4xl">
          바로 쓰는 광고 템플릿 {CATALOG.length}종
        </h2>
        <p className="mt-4 max-w-xl leading-7 text-muted">
          원하는 연출을 고르면 스타일·용도가 자동으로 맞춰집니다. 마음에 드는 카드를
          눌러 바로 시작해 보세요.
        </p>
      </Reveal>
      <div className="flex flex-col gap-4">
        <Row items={rowA} duration="70s" />
        <Row items={rowB} reverse duration="82s" />
      </div>
    </section>
  );
}
