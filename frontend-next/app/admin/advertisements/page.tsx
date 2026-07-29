"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ImageIcon, RefreshCw, Search, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminAdvertisement,
  type AdminListResponse,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

const PAGE_SIZE = 30;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusClass(status: string): string {
  if (status === "completed") return "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]";
  if (status === "failed") return "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]";
  return "border-[#fbbf24]/35 bg-[#fbbf24]/10 text-[#fde68a]";
}

function statusLabel(status: string): string {
  if (status === "completed") return "생성 완료";
  if (status === "failed") return "생성 실패";
  return status;
}

function AdminAdvertisementImage({ advertisementId, alt }: { advertisementId: number; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    async function loadImage() {
      try {
        const response = await adminApiFetch(`/admin/advertisements/${advertisementId}/image`);
        if (!response.ok) throw new Error();
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) setSrc(objectUrl);
      } catch {
        if (!cancelled) setSrc(null);
      }
    }

    void loadImage();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [advertisementId]);

  if (!src) {
    return <div className="grid h-20 w-20 shrink-0 place-items-center bg-white/[0.04] text-[11px] text-white/35">이미지 없음</div>;
  }

  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className="h-20 w-20 shrink-0 object-cover" />;
}

export default function AdminAdvertisementsPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [advertisements, setAdvertisements] = useState<AdminAdvertisement[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [appliedStatus, setAppliedStatus] = useState("all");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  const loadAdvertisements = useCallback(async () => {
    const params = new URLSearchParams({
      skip: String(page * PAGE_SIZE),
      limit: String(PAGE_SIZE),
    });
    if (appliedSearch.trim()) params.set("search", appliedSearch.trim());
    if (appliedStatus !== "all") params.set("status", appliedStatus);

    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/advertisements?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminAdvertisement> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "광고 목록을 불러오지 못했습니다."));
      }
      setAdvertisements(data.items);
      setTotal(data.total);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "광고 목록을 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, appliedStatus, page]);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadAdvertisements();
  }, [admin, loadAdvertisements, ready]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(0);
    setAppliedSearch(search);
    setAppliedStatus(status);
  }

  async function deleteAdvertisement(advertisement: AdminAdvertisement) {
    if (admin?.role !== "super_admin") {
      setMessage("광고 삭제는 최고 관리자만 할 수 있습니다.");
      setMessageKind("error");
      return;
    }
    const label = advertisement.title || `광고 #${advertisement.id}`;
    if (!window.confirm(`${label}을(를) 삭제할까요? 생성 이미지와 광고 이력이 함께 삭제됩니다.`)) return;

    setDeletingId(advertisement.id);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/advertisements/${advertisement.id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const data = await readJsonSafely(response);
        throw new Error(readApiError(data, "광고를 삭제하지 못했습니다."));
      }
      setAdvertisements((items) => items.filter((item) => item.id !== advertisement.id));
      setTotal((value) => Math.max(0, value - 1));
      setMessage("광고와 연결된 생성 결과를 삭제했습니다.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "광고를 삭제하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setDeletingId(null);
    }
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  const canDelete = admin.role === "super_admin";

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">CONTENT</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">광고 관리</h1>
            <p className="mt-2 text-sm text-white/50">전체 생성 광고를 확인하고 부적절한 결과를 정리합니다.</p>
          </div>
          <button type="button" onClick={() => void loadAdvertisements()} disabled={loading} className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-60">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        <form onSubmit={applyFilters} className="mt-7 grid gap-3 rounded-2xl border border-white/10 bg-[#102039]/90 p-4 lg:grid-cols-[minmax(0,1fr)_10rem_auto]">
          <label className="relative block">
            <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
            <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="상품명, 생성자 아이디, 이메일 검색" className="h-11 w-full border border-white/15 bg-[#0b1729] pl-10 pr-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]" />
          </label>
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]">
            <option value="all">전체 상태</option>
            <option value="completed">생성 완료</option>
            <option value="failed">생성 실패</option>
          </select>
          <button type="submit" disabled={loading} className="h-11 bg-[#8b5cf6] px-5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60">적용</button>
        </form>

        {!canDelete && <p className="mt-4 text-sm text-white/45">광고 삭제는 최고 관리자만 할 수 있습니다.</p>}
        {message && <p role={messageKind === "error" ? "alert" : "status"} className={`mt-5 border px-4 py-3 text-sm ${messageKind === "error" ? "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]" : "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]"}`}>{message}</p>}

        <section className="mt-7 overflow-hidden rounded-2xl border border-white/10 bg-[#102039]/90">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div className="flex items-center gap-2"><ImageIcon size={18} className="text-[#a78bfa]" /><h2 className="text-sm font-bold">생성 광고</h2></div>
            <span className="text-sm text-white/50">총 {total.toLocaleString("ko-KR")}건</span>
          </div>
          <div className="divide-y divide-white/10">
            {loading && advertisements.length === 0 ? (
              <p className="px-5 py-14 text-center text-sm text-white/45">광고 목록을 불러오고 있습니다.</p>
            ) : advertisements.length === 0 ? (
              <p className="px-5 py-14 text-center text-sm text-white/45">조건에 맞는 광고가 없습니다.</p>
            ) : advertisements.map((advertisement) => (
              <article key={advertisement.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
                {advertisement.output_image_id ? <AdminAdvertisementImage advertisementId={advertisement.id} alt={advertisement.title || "생성 광고"} /> : <div className="grid h-20 w-20 shrink-0 place-items-center bg-white/[0.04] text-[11px] text-white/35">이미지 없음</div>}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><h3 className="truncate font-bold text-white">{advertisement.title || "상품명 없음"}</h3><span className={`border px-2 py-1 text-[11px] font-bold ${statusClass(advertisement.status)}`}>{statusLabel(advertisement.status)}</span></div>
                  <p className="mt-2 text-sm text-white/55">{advertisement.username} · {advertisement.email}</p>
                  <p className="mt-1 text-xs text-white/40">{advertisement.style || "스타일 없음"} · {advertisement.ad_type} · {formatDate(advertisement.created_at)}</p>
                </div>
                {canDelete && <button type="button" disabled={deletingId === advertisement.id} onClick={() => void deleteAdvertisement(advertisement)} className="inline-flex h-10 items-center gap-2 border border-[#f87171]/35 px-3 text-sm font-bold text-[#fecaca] transition hover:bg-[#f87171]/10 disabled:cursor-not-allowed disabled:opacity-60"><Trash2 size={16} />{deletingId === advertisement.id ? "삭제 중" : "강제 삭제"}</button>}
              </article>
            ))}
          </div>
          <div className="flex items-center justify-between border-t border-white/10 px-5 py-4 text-sm">
            <button type="button" disabled={page === 0 || loading} onClick={() => setPage((value) => Math.max(0, value - 1))} className="border border-white/15 px-3 py-2 font-bold text-white/75 disabled:cursor-not-allowed disabled:opacity-40">이전</button>
            <span className="text-white/45">{page + 1} / {lastPage + 1} 페이지</span>
            <button type="button" disabled={page >= lastPage || loading} onClick={() => setPage((value) => Math.min(lastPage, value + 1))} className="border border-white/15 px-3 py-2 font-bold text-white/75 disabled:cursor-not-allowed disabled:opacity-40">다음</button>
          </div>
        </section>
      </section>
    </AdminShell>
  );
}
