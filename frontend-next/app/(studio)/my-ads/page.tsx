"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdItem, normalizePlatformCopy } from "@/lib/api";
import { SNS_LIST, deleteStoredAd, exportSnsPost } from "@/lib/sns";
import { useStudio } from "@/components/studio/StudioProvider";
import { AppBar } from "@/components/studio/chrome";
import { AuthenticatedImage } from "@/components/studio/AuthenticatedImage";

const FILTERS = ["all", "모노톤", "웜 빈티지", "팝 비비드", "에디토리얼", "리얼리즘", "파스텔"];

export default function MyAdsPage() {
  const s = useStudio();
  const router = useRouter();
  const [filter, setFilter] = useState("all");
  const [openSns, setOpenSns] = useState<number | null>(null);

  useEffect(() => {
    if (s.ready && !s.token) router.replace("/login");
  }, [s.ready, s.token, router]);

  useEffect(() => {
    s.refreshHistory(true);
    s.refreshDashboardSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const close = () => setOpenSns(null);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const list = s.ads.filter((a) => filter === "all" || a.style === filter);

  function openDetail(item: AdItem) {
    s.openDetail(item);
    router.push(item.historyId ? `/detail?historyId=${item.historyId}` : "/detail");
  }

  async function share(platformName: string, platform: string, item: AdItem) {
    setOpenSns(null);
    const copy = normalizePlatformCopy(item.platformCopies?.[platform], {
      head: item.copyHead || item.hl || "",
      body: item.copyBody || "",
      tags: item.copyTags || "",
    });
    await exportSnsPost(
      platform,
      { ...item, copyHead: copy.head, copyBody: copy.body, copyTags: copy.tags },
      s.toast
    );
  }

  async function delCard(item: AdItem) {
    try {
      await deleteStoredAd(item.historyId);
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "광고 삭제에 실패했습니다");
      return;
    }
    s.setAds(s.ads.filter((a) => a !== item));
    s.refreshDashboardSummary();
    s.toast("광고를 삭제했어요");
  }

  return (
    <section>
      <AppBar />
      <div className="page">
        <div className="page-head">
          <div>
            <h2>내 광고</h2>
            <p className="lead">만든 광고를 다시 보고, SNS에 공유하거나 정리할 수 있어요.</p>
          </div>
        </div>

        <div className="filters">
          {FILTERS.map((f) => (
            <button
              key={f}
              className={`fchip${filter === f ? " on" : ""}`}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "전체" : f}
            </button>
          ))}
        </div>

        <div className="cards-grid">
          {list.length === 0 ? (
            <div className="empty-my">
              <div className="big">🗂</div>
              <h3>{filter === "all" ? "아직 만든 광고가 없어요" : "이 스타일 광고가 없어요"}</h3>
              <p>다른 스타일을 골라보거나 새 광고를 만들어보세요.</p>
            </div>
          ) : (
            list.map((a, gi) => (
              <div
                key={a.historyId ?? gi}
                className="ad-card"
                role="button"
                tabIndex={0}
                onClick={() => openDetail(a)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") openDetail(a);
                }}
              >
                <div className="cpic" style={{ background: a.g }}>
                  <span className="st-tag">{a.style}</span>
                  {a.img ? (
                    <AuthenticatedImage className="cimg" src={a.img} alt={a.hl} />
                  ) : (
                    <>
                      <div className="prod" style={{ background: a.prod }}>
                        {a.emoji}
                      </div>
                      <div className="hl">{a.hl}</div>
                    </>
                  )}
                </div>
                <div className="cbody">
                  <div className="cmeta">
                    <span className="st">{a.style} 스타일</span>
                    <span className="dt">{a.date}</span>
                  </div>
                  <div className="card-actions">
                    <div className="share-wrap">
                      <button
                        className="a-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenSns(openSns === gi ? null : gi);
                        }}
                      >
                        ↗️ SNS 공유
                      </button>
                      <div className={`sns-menu${openSns === gi ? " on" : ""}`}>
                        {SNS_LIST.map((sns) => (
                          <button
                            key={sns.k}
                            onClick={(e) => {
                              e.stopPropagation();
                              share(sns.n, sns.p, a);
                            }}
                          >
                            <span className={`si ${sns.k}`}>{sns.n[0]}</span>
                            {sns.n}에 공유
                          </button>
                        ))}
                      </div>
                    </div>
                    <button
                      className="a-btn del"
                      title="삭제"
                      onClick={(e) => {
                        e.stopPropagation();
                        delCard(a);
                      }}
                    >
                      🗑
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
