"use client";

/* 고객센터 챗봇 팝업(노바냥) — 우측 하단 상시 노출 (root layout 전역 마운트).
   API: POST {API_BASE_URL}/support/chat (backend/app/api/chatbot.py 계약,
   main.py 라우터 등록 전에는 404 → FAQ 안내로 우아하게 폴백).
   에스컬레이션 응답은 1:1 문의 초안을 포함 — /support 문의 폼으로 유도. */

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { API_BASE_URL } from "@/lib/api";
import CatIcon from "./CatIcon";

type InquiryDraft = { title: string; content: string; category_hint?: string | null };
type ChatResponse = {
  answer: string;
  escalate: boolean;
  sources: string[];
  inquiry_draft?: InquiryDraft | null;
};
type Message = {
  role: "user" | "bot";
  text: string;
  sources?: string[];
  draft?: InquiryDraft | null;
  failed?: boolean;
};

const GREETING =
  "안녕하세요, AdNova 고양이 상담사 노바냥이에요 🐾\n요금·사용법·사진 팁 등 궁금한 걸 물어보세요. 제가 모르는 건 1:1 문의로 이어드릴게요.";

// KB 카테고리 → /support 문의 폼 카테고리 코드 매핑 (프리필용)
const CATEGORY_CODE: Record<string, string> = {
  "요금·크레딧": "billing",
  계정: "account",
  "서비스 이용": "generation",
  "사진·품질": "generation",
};

function draftHref(draft: InquiryDraft): string {
  const params = new URLSearchParams({
    dtitle: draft.title,
    dcontent: draft.content,
    dcat: CATEGORY_CODE[draft.category_hint ?? ""] ?? "general",
  });
  return `/support?${params.toString()}`;
}

export default function ChatWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<Message[]>([{ role: "bot", text: GREETING }]);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, open]);

  if (pathname.startsWith("/admin")) return null;

  async function send() {
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE_URL}/support/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ChatResponse = await res.json();
      setMessages((m) => [
        ...m,
        { role: "bot", text: data.answer, sources: data.sources, draft: data.inquiry_draft },
      ]);
    } catch {
      setMessages((m) => [
        ...m,
        {
          role: "bot",
          text: "앗, 지금은 상담 연결이 어려워요 😿 고객센터의 자주 묻는 질문에서 먼저 찾아보시겠어요?",
          failed: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-[90] flex flex-col items-end gap-3">
      {open && (
        <div className="flex h-[520px] w-[min(360px,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50">
          {/* 헤더 */}
          <div className="flex items-center gap-3 accent-gradient px-4 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20">
              <CatIcon className="h-7 w-7" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-bold text-white">노바냥 · 고객센터</p>
              <p className="text-[11px] text-white/80">AI 상담사가 바로 답해드려요</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="챗봇 닫기"
              className="rounded-full p-1 text-white/80 transition-colors hover:bg-white/15 hover:text-white"
            >
              <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          {/* 메시지 */}
          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-3 py-4">
            {messages.map((msg, i) =>
              msg.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl rounded-br-md accent-gradient px-3.5 py-2.5 text-sm text-white">
                    {msg.text}
                  </div>
                </div>
              ) : (
                <div key={i} className="flex items-end gap-2">
                  <div className="h-7 w-7 shrink-0 rounded-full bg-accent/20 p-1">
                    <CatIcon className="h-full w-full" />
                  </div>
                  <div className="max-w-[82%] space-y-2">
                    <div className="whitespace-pre-line rounded-2xl rounded-bl-md border border-border bg-background/60 px-3.5 py-2.5 text-sm text-soft">
                      {msg.text}
                    </div>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {msg.sources.map((s) => (
                          <a
                            key={s}
                            href={`/support#${s}`}
                            className="rounded-full border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-[11px] text-accent-deep transition-colors hover:bg-accent/20"
                          >
                            근거 FAQ 보기 →
                          </a>
                        ))}
                      </div>
                    )}
                    {msg.draft && (
                      <div className="rounded-xl border border-accent/30 bg-accent/10 p-3 text-xs text-soft">
                        <p className="mb-1 font-semibold text-foreground">1:1 문의 초안을 만들어뒀어요</p>
                        <p className="mb-2 line-clamp-3 whitespace-pre-line text-muted">{msg.draft.content}</p>
                        <div className="flex gap-2">
                          <button
                            onClick={() =>
                              navigator.clipboard?.writeText(`[${msg.draft!.title}]\n${msg.draft!.content}`)
                            }
                            className="rounded-full border border-accent/40 px-3 py-1 text-[11px] font-semibold text-accent-deep"
                          >
                            초안 복사
                          </button>
                          <a
                            href={draftHref(msg.draft)}
                            className="rounded-full accent-gradient px-3 py-1 text-[11px] font-semibold text-white"
                          >
                            1:1 문의 작성하기
                          </a>
                        </div>
                      </div>
                    )}
                    {msg.failed && (
                      <a
                        href="/support"
                        className="inline-block rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-[11px] text-accent-deep transition-colors hover:bg-accent/20"
                      >
                        자주 묻는 질문 보기 →
                      </a>
                    )}
                  </div>
                </div>
              )
            )}
            {busy && (
              <div className="flex items-center gap-2 pl-9 text-xs text-muted">
                <span className="inline-flex gap-1">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:0ms]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:120ms]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:240ms]" />
                </span>
                노바냥이 답변을 준비 중…
              </div>
            )}
          </div>

          {/* 입력 */}
          <div className="border-t border-border p-3">
            <div className="flex items-center gap-2 rounded-full border border-border bg-background/60 px-3 py-1.5 focus-within:border-accent/50">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing) send();
                }}
                placeholder="궁금한 걸 물어보세요"
                maxLength={1000}
                className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted focus:outline-none"
              />
              <button
                onClick={send}
                disabled={busy || !input.trim()}
                aria-label="질문 보내기"
                className="flex h-8 w-8 items-center justify-center rounded-full accent-gradient text-white transition-opacity disabled:opacity-40"
              >
                <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                  <path d="M2.5 10 L17 3 L12.5 10 L17 17 Z" />
                </svg>
              </button>
            </div>
            <p className="mt-1.5 text-center text-[10px] text-muted">
              답을 못 찾으면 1:1 문의 초안까지 만들어드려요
            </p>
          </div>
        </div>
      )}

      {/* 고양이 런처 버튼 */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "챗봇 닫기" : "고객센터 챗봇 열기"}
        className="group relative flex h-14 w-14 items-center justify-center rounded-full accent-gradient shadow-lg shadow-accent/40 transition-transform hover:scale-105"
      >
        <CatIcon className="h-10 w-10 transition-transform group-hover:-rotate-6" />
        {!open && (
          <span className="absolute -top-0.5 right-0 h-3 w-3 rounded-full bg-ok ring-2 ring-background" />
        )}
      </button>
    </div>
  );
}
