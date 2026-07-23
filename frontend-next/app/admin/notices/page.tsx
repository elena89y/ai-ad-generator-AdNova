"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { FilePlus2, Megaphone, PencilLine, RefreshCw, Search, Send, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import { type AdminListResponse, type AdminNotice, adminApiFetch } from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

type NoticeFilters = {
  search: string;
  published: "all" | "published" | "draft";
};

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function matchesNoticeFilters(notice: AdminNotice, filters: NoticeFilters): boolean {
  if (filters.published === "published" && !notice.is_published) return false;
  if (filters.published === "draft" && notice.is_published) return false;
  const keyword = filters.search.trim().toLowerCase();
  return !keyword || `${notice.title} ${notice.content}`.toLowerCase().includes(keyword);
}

export default function AdminNoticesPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [notices, setNotices] = useState<AdminNotice[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [published, setPublished] = useState<NoticeFilters["published"]>("all");
  const [appliedFilters, setAppliedFilters] = useState<NoticeFilters>({ search: "", published: "all" });
  const [selected, setSelected] = useState<AdminNotice | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [isPublished, setIsPublished] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  const loadNotices = useCallback(async (filters: NoticeFilters) => {
    const params = new URLSearchParams({ limit: "100" });
    const keyword = filters.search.trim();
    if (keyword) params.set("search", keyword);
    if (filters.published !== "all") {
      params.set("is_published", String(filters.published === "published"));
    }

    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/notices?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminNotice> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "공지사항 목록을 불러오지 못했습니다."));
      }
      setNotices(data.items);
      setTotal(data.total);
      setSelected((current) => data.items.find((item) => item.id === current?.id) || null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "공지사항 목록을 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadNotices(appliedFilters);
  }, [admin, appliedFilters, loadNotices, ready]);

  useEffect(() => {
    if (!selected) {
      setTitle("");
      setContent("");
      setIsPublished(false);
      return;
    }
    setTitle(selected.title);
    setContent(selected.content);
    setIsPublished(selected.is_published);
  }, [selected]);

  function startNewNotice() {
    setSelected(null);
    setTitle("");
    setContent("");
    setIsPublished(false);
    setMessage("");
    setMessageKind(null);
  }

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters({ search, published });
  }

  async function saveNotice() {
    const trimmedTitle = title.trim();
    const trimmedContent = content.trim();
    if (!trimmedTitle || !trimmedContent) {
      setMessage("공지 제목과 내용을 모두 입력해 주세요.");
      setMessageKind("error");
      return;
    }

    setSaving(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(selected ? `/admin/notices/${selected.id}` : "/admin/notices", {
        method: selected ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmedTitle, content: trimmedContent, is_published: isPublished }),
      });
      const data = (await readJsonSafely(response)) as AdminNotice | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "공지사항을 저장하지 못했습니다."));
      }

      await loadNotices(appliedFilters);
      setSelected(matchesNoticeFilters(data, appliedFilters) ? data : null);
      setMessage(isPublished ? "공지사항을 게시했습니다." : "공지사항을 임시 저장했습니다.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "공지사항을 저장하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setSaving(false);
    }
  }

  async function deleteSelectedNotice() {
    if (!selected || !window.confirm(`'${selected.title}' 공지사항을 삭제할까요?`)) return;

    setDeleting(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/notices/${selected.id}`, { method: "DELETE" });
      const data = await readJsonSafely(response);
      if (!response.ok) {
        throw new Error(readApiError(data, "공지사항을 삭제하지 못했습니다."));
      }
      setNotices((current) => current.filter((item) => item.id !== selected.id));
      setTotal((current) => Math.max(0, current - 1));
      startNewNotice();
      setMessage("공지사항을 삭제했습니다.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "공지사항을 삭제하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setDeleting(false);
    }
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">CONTENT</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">공지사항 관리</h1>
            <p className="mt-2 text-sm text-white/50">임시 저장한 뒤 필요한 시점에 사용자 공지로 게시할 수 있습니다.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={startNewNotice} className="inline-flex h-10 items-center gap-2 border border-[#a78bfa]/50 px-4 text-sm font-bold text-[#ddd6fe] transition hover:bg-[#8b5cf6]/15">
              <FilePlus2 size={16} />새 공지
            </button>
            <button type="button" onClick={() => void loadNotices(appliedFilters)} disabled={loading} className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-60">
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />새로고침
            </button>
          </div>
        </div>

        <form onSubmit={handleFilterSubmit} className="mt-7 grid gap-3 rounded-2xl border border-white/10 bg-[#102039]/90 p-4 lg:grid-cols-[minmax(0,1fr)_10rem_auto]">
          <label className="relative block">
            <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
            <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="제목 또는 내용 검색" className="h-11 w-full border border-white/15 bg-[#0b1729] pl-10 pr-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]" />
          </label>
          <select value={published} onChange={(event) => setPublished(event.target.value as NoticeFilters["published"])} className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]">
            <option value="all">전체 상태</option>
            <option value="published">게시됨</option>
            <option value="draft">임시 저장</option>
          </select>
          <button type="submit" disabled={loading} className="h-11 bg-[#8b5cf6] px-5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60">적용</button>
        </form>

        {message && (
          <p role={messageKind === "error" ? "alert" : "status"} className={`mt-5 border px-4 py-3 text-sm ${messageKind === "error" ? "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]" : "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]"}`}>{message}</p>
        )}

        <div className="mt-7 grid gap-3 xl:grid-cols-[minmax(0,0.9fr)_minmax(400px,1.1fr)]">
          <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#102039]/90">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex items-center gap-2"><Megaphone size={18} className="text-[#a78bfa]" /><h2 className="text-sm font-bold">공지 목록</h2></div>
              <span className="text-sm text-white/50">총 {total.toLocaleString("ko-KR")}건</span>
            </div>
            <div className="divide-y divide-white/10">
              {loading && notices.length === 0 ? (
                <p className="px-5 py-14 text-center text-sm text-white/45">공지사항을 불러오고 있습니다.</p>
              ) : notices.length === 0 ? (
                <p className="px-5 py-14 text-center text-sm text-white/45">등록된 공지사항이 없습니다.</p>
              ) : (
                notices.map((notice) => (
                  <button key={notice.id} type="button" onClick={() => { setSelected(notice); setMessage(""); setMessageKind(null); }} className={`w-full px-5 py-4 text-left transition hover:bg-white/[0.025] ${selected?.id === notice.id ? "bg-[#8b5cf6]/10" : ""}`}>
                    <div className="flex items-start justify-between gap-3">
                      <p className="min-w-0 truncate font-bold text-white">{notice.title}</p>
                      <span className={`shrink-0 border px-2 py-1 text-[11px] font-bold ${notice.is_published ? "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]" : "border-white/15 bg-white/5 text-white/50"}`}>{notice.is_published ? "게시됨" : "임시 저장"}</span>
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-white/55">{notice.content}</p>
                    <p className="mt-3 text-xs text-white/35">{notice.is_published ? `게시 ${formatDate(notice.published_at)}` : `작성 ${formatDate(notice.created_at)}`}</p>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2"><PencilLine size={18} className="text-[#a78bfa]" /><h2 className="text-sm font-bold">{selected ? "공지사항 수정" : "새 공지사항"}</h2></div>
              {selected && <span className="text-xs text-white/35">#{selected.id}</span>}
            </div>
            <div className="mt-6 grid gap-4">
              <label className="grid gap-1.5 text-xs font-semibold text-white/55">제목<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={255} placeholder="공지 제목을 입력해 주세요." className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm font-normal text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]" /></label>
              <label className="grid gap-1.5 text-xs font-semibold text-white/55">내용<textarea value={content} onChange={(event) => setContent(event.target.value)} maxLength={10000} rows={13} placeholder="사용자에게 전달할 공지 내용을 입력해 주세요." className="resize-y border border-white/15 bg-[#0b1729] px-3 py-3 text-sm font-normal leading-6 text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]" /><span className="text-right text-[11px] font-normal text-white/35">{content.length.toLocaleString("ko-KR")} / 10,000</span></label>
              <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-white/10 bg-[#0b1729] px-4 py-3 text-sm text-white/75"><input type="checkbox" checked={isPublished} onChange={(event) => setIsPublished(event.target.checked)} className="size-4 accent-[#8b5cf6]" />저장과 함께 사용자 공지사항에 게시</label>
            </div>
            <div className="mt-6 flex flex-wrap justify-between gap-2">
              {selected ? (
                <button type="button" onClick={() => void deleteSelectedNotice()} disabled={saving || deleting} className="inline-flex h-10 items-center gap-2 border border-[#f87171]/45 px-4 text-sm font-bold text-[#fca5a5] transition hover:bg-[#f87171]/10 disabled:cursor-not-allowed disabled:opacity-60"><Trash2 size={16} />{deleting ? "삭제 중..." : "삭제"}</button>
              ) : <span />}
              <button type="button" onClick={() => void saveNotice()} disabled={saving || deleting} className="inline-flex h-10 items-center gap-2 bg-[#8b5cf6] px-4 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"><Send size={16} />{saving ? "저장 중..." : isPublished ? "게시하기" : "임시 저장"}</button>
            </div>
          </section>
        </div>
      </section>
    </AdminShell>
  );
}
