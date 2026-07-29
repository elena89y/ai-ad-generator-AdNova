"use client";

import { useEffect, useState } from "react";

import { SubBar } from "@/components/studio/chrome";
import { apiFetch, readApiError, readJsonSafely } from "@/lib/api";

interface NoticeItem {
  id: number;
  title: string;
  content: string;
  published_at: string;
  created_at: string;
  updated_at: string;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

export default function NoticesPage() {
  const [notices, setNotices] = useState<NoticeItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadNotices() {
      const requestedNoticeId = Number(
        new URLSearchParams(window.location.search).get("notice"),
      );
      setLoading(true);
      setError("");
      try {
        const response = await apiFetch("/notices?limit=50");
        const data = (await readJsonSafely(response)) as { items?: NoticeItem[] } | null;
        if (!response.ok || !data) {
          throw new Error(readApiError(data, "공지사항을 불러오지 못했습니다."));
        }
        if (cancelled) return;

        const items = data.items || [];
        setNotices(items);
        setSelectedId(
          items.some((item) => item.id === requestedNoticeId)
            ? requestedNoticeId
            : items[0]?.id || null,
        );
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "공지사항을 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadNotices();
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = notices.find((item) => item.id === selectedId) || null;

  return (
    <section>
      <SubBar />
      <div className="page" style={{ maxWidth: 920 }}>
        <header style={{ margin: "10px 0 28px" }}>
          <p style={{ margin: 0, fontSize: 12, fontWeight: 800, letterSpacing: ".1em", color: "var(--gold)" }}>NOTICE</p>
          <h2 style={{ margin: "8px 0 7px", fontSize: 28, fontWeight: 800, letterSpacing: "-.5px" }}>공지사항</h2>
          <p style={{ margin: 0, color: "var(--ink-mute)", fontSize: 13 }}>AdNova의 새로운 소식과 서비스 안내를 확인하세요.</p>
        </header>

        {loading ? (
          <div style={{ padding: 28, border: "1px solid var(--line)", borderRadius: 14, color: "var(--ink-mute)", textAlign: "center", fontSize: 13 }}>공지사항을 불러오는 중입니다.</div>
        ) : error ? (
          <div role="alert" style={{ padding: 18, border: "1px solid rgba(248,113,113,.45)", borderRadius: 14, color: "#fca5a5", fontSize: 13 }}>{error}</div>
        ) : notices.length === 0 ? (
          <div style={{ padding: 28, border: "1px solid var(--line)", borderRadius: 14, color: "var(--ink-mute)", textAlign: "center", fontSize: 13 }}>게시된 공지사항이 없습니다.</div>
        ) : (
          <div className="notice-layout" style={{ display: "grid", gridTemplateColumns: "minmax(230px,.7fr) minmax(0,1.3fr)", gap: 14, alignItems: "start" }}>
            <aside style={{ overflow: "hidden", border: "1px solid var(--line)", borderRadius: 14, background: "#211F27" }}>
              {notices.map((notice) => (
                <button
                  key={notice.id}
                  type="button"
                  onClick={() => setSelectedId(notice.id)}
                  style={{ width: "100%", display: "block", padding: "16px", border: 0, borderBottom: "1px solid var(--line)", background: selectedId === notice.id ? "rgba(242,169,59,.11)" : "transparent", color: "var(--ink)", textAlign: "left", cursor: "pointer" }}
                >
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 13, fontWeight: 800 }}>{notice.title}</div>
                  <div style={{ marginTop: 6, color: "var(--ink-mute)", fontSize: 11.5 }}>{formatDate(notice.published_at)}</div>
                </button>
              ))}
            </aside>
            {selected && (
              <article style={{ minHeight: 300, border: "1px solid var(--line)", borderRadius: 14, background: "#211F27", padding: "clamp(20px,4vw,34px)" }}>
                <p style={{ margin: 0, color: "var(--gold)", fontSize: 12, fontWeight: 800 }}>공지</p>
                <h3 style={{ margin: "10px 0 8px", fontSize: 22, lineHeight: 1.4 }}>{selected.title}</h3>
                <p style={{ margin: 0, color: "var(--ink-mute)", fontSize: 12 }}>{formatDate(selected.published_at)}</p>
                <div style={{ marginTop: 24, paddingTop: 22, borderTop: "1px solid var(--line)", whiteSpace: "pre-wrap", color: "var(--ink-soft)", fontSize: 14, lineHeight: 1.8 }}>{selected.content}</div>
              </article>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
