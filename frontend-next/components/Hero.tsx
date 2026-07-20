"use client";

import { motion } from "framer-motion";
import { ArrowRight, PlayCircle } from "lucide-react";

export default function Hero() {
  return (
    <section id="top" className="relative flex min-h-screen items-center overflow-hidden">
      <video
        className="absolute inset-0 h-full w-full object-cover"
        src="/media/hero-bg.mp4"
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
      />

      <div className="absolute inset-0 bg-gradient-to-b from-black/70 via-black/55 to-background" />
      <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-black/40" />
      <div className="noise absolute inset-0" />

      <div className="relative z-10 mx-auto w-full max-w-6xl px-6 pt-28 pb-20">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="glass mb-6 inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs text-soft"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          소상공인을 위한 AI 광고 생성 플랫폼
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="max-w-4xl text-5xl font-extrabold leading-[1.08] tracking-tight sm:text-6xl md:text-7xl"
        >
          제품 사진 한 장이
          <br />
          <em className="serif-accent text-gradient font-normal">
            광고
          </em>
          가 되기까지, <span className="text-gradient">몇 초.</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="mt-6 max-w-xl text-lg text-white/70"
        >
          사진 올리고, 원하는 걸 한 줄 적고, 스타일만 고르세요. 광고 문구와
          이미지는 AI가 만들어 드려요. 디자이너도, 마케터도 필요 없습니다.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.3 }}
          className="mt-9 flex flex-wrap items-center gap-4"
        >
          <a
            href="/signup"
            className="group flex items-center gap-2 rounded-full accent-gradient px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-berry/25 transition-transform hover:scale-[1.03]"
          >
            무료로 시작하기
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
          </a>
          <a
            href="#showcase"
            className="flex items-center gap-2 rounded-full border border-white/20 px-6 py-3.5 text-sm font-medium text-white/90 transition-colors hover:bg-white/10"
          >
            <PlayCircle className="h-4 w-4" />
            예시 보기
          </a>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.45 }}
          className="mt-16 grid max-w-2xl grid-cols-3 gap-4 sm:gap-8"
        >
          {[
            { value: "6종", label: "광고 스타일 프리셋" },
            { value: "4단계", label: "자동 생성 파이프라인" },
            { value: "3개", label: "가입 즉시 무료 크레딧" },
          ].map((s) => (
            <div key={s.label}>
              <div className="font-display text-2xl font-bold sm:text-3xl">
                {s.value}
              </div>
              <div className="mt-1 text-xs text-white/50 sm:text-sm">{s.label}</div>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
