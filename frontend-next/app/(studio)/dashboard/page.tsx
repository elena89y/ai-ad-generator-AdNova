"use client";

import type { CSSProperties } from "react";
import { useRouter } from "next/navigation";
import { useStudio } from "@/components/studio/StudioProvider";

const QUICK_LINKS = [
  {
    title: "광고 만들기",
    description: "새로운 AI 광고를 생성해요",
    icon: "✦",
    href: "/studio",
  },
  {
    title: "내 광고",
    description: "저장된 광고를 확인해요",
    icon: "▣",
    href: "/my-ads",
  },
  {
    title: "요금제",
    description: "구독과 사용량을 관리해요",
    icon: "◇",
    href: "/billing",
  },
  {
    title: "설정",
    description: "계정 정보를 관리해요",
    icon: "⚙",
    href: "/settings",
  },
];

export default function DashboardPage() {
  const router = useRouter();
  const studio = useStudio();

  const ads = studio.ads ?? [];
  const recentAds = ads.slice(0, 3);
  const totalAds = ads.length;

  if (!studio.ready) {
    return (
      <main style={styles.loading}>
        대시보드를 불러오는 중입니다.
      </main>
    );
  }

  return (
    <main style={styles.page}>
      <div style={styles.backgroundGlowOne} />
      <div style={styles.backgroundGlowTwo} />

      <div style={styles.container}>
        {/* 상단 인사말 */}
        <section style={styles.hero}>
          <div>
            <div style={styles.eyebrow}>ADNOVA DASHBOARD</div>

            <h1 style={styles.title}>
              오늘도 멋진 광고를
              <br />
              만들어볼까요?
            </h1>

            <p style={styles.subtitle}>
              제품 사진 한 장으로 이미지와 광고 문구를 완성해보세요.
            </p>
          </div>

          <button
            type="button"
            style={styles.primaryButton}
            onClick={() => router.push("/studio")}
          >
            <span style={styles.buttonSpark}>✦</span>
            새 광고 만들기
          </button>
        </section>

        {/* 통계 */}
        <section style={styles.statsGrid}>
          <article style={styles.statCard}>
            <span style={styles.statLabel}>전체 광고</span>
            <strong style={styles.statNumber}>{totalAds}</strong>
            <span style={styles.statDescription}>생성된 광고</span>
          </article>

          <article style={styles.statCard}>
            <span style={styles.statLabel}>최근 작업</span>
            <strong style={styles.statNumber}>{recentAds.length}</strong>
            <span style={styles.statDescription}>빠르게 다시 확인</span>
          </article>

          <article style={styles.statCard}>
            <span style={styles.statLabel}>현재 플랜</span>
            <strong style={styles.planText}>
              {studio.isPremium ? "Premium" : "Free"}
            </strong>
            <span style={styles.statDescription}>
              {studio.isPremium ? "프리미엄 기능 사용 중" : "무료 플랜 사용 중"}
            </span>
          </article>
        </section>

        {/* 하단 콘텐츠 */}
        <section style={styles.contentGrid}>
          {/* 최근 광고 */}
          <article style={styles.panel}>
            <div style={styles.panelHeader}>
              <div>
                <span style={styles.sectionLabel}>RECENT WORK</span>
                <h2 style={styles.panelTitle}>최근 광고</h2>
              </div>

              <button
                type="button"
                style={styles.textButton}
                onClick={() => router.push("/my-ads")}
              >
                전체 보기 →
              </button>
            </div>

            {recentAds.length > 0 ? (
              <div style={styles.recentGrid}>
                {recentAds.map((item, index) => (
                  <button
                    type="button"
                    key={`${item.historyId ?? "ad"}-${index}`}
                    style={styles.adCard}
                    onClick={() => {
                      studio.openDetail(item);

                      if (item.historyId) {
                        router.push(`/detail?historyId=${item.historyId}`);
                      } else {
                        router.push("/detail");
                      }
                    }}
                  >
                    <div style={styles.imageWrap}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={item.img}
                        alt={item.productName || "생성된 광고"}
                        style={styles.image}
                      />

                      <span style={styles.aiBadge}>AI</span>
                    </div>

                    <div style={styles.adInfo}>
                      <strong style={styles.adTitle}>
                        {item.productName || item.hl || "새 광고"}
                      </strong>

                      <span style={styles.adDate}>
                        {item.date || "날짜 정보 없음"}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div style={styles.emptyState}>
                <div style={styles.emptyIcon}>✦</div>

                <h3 style={styles.emptyTitle}>
                  아직 생성된 광고가 없어요
                </h3>

                <p style={styles.emptyDescription}>
                  첫 번째 AI 광고를 만들어보세요.
                </p>

                <button
                  type="button"
                  style={styles.emptyButton}
                  onClick={() => router.push("/studio")}
                >
                  광고 만들기
                </button>
              </div>
            )}
          </article>

          {/* 빠른 메뉴 */}
          <aside style={styles.panel}>
            <div style={styles.panelHeader}>
              <div>
                <span style={styles.sectionLabel}>QUICK ACCESS</span>
                <h2 style={styles.panelTitle}>빠른 메뉴</h2>
              </div>
            </div>

            <div style={styles.quickLinkList}>
              {QUICK_LINKS.map((link) => (
                <button
                  type="button"
                  key={link.href}
                  style={styles.quickLink}
                  onClick={() => router.push(link.href)}
                >
                  <span style={styles.quickIcon}>{link.icon}</span>

                  <span style={styles.quickText}>
                    <strong style={styles.quickTitle}>
                      {link.title}
                    </strong>

                    <span style={styles.quickDescription}>
                      {link.description}
                    </span>
                  </span>

                  <span style={styles.quickArrow}>→</span>
                </button>
              ))}
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    position: "relative",
    minHeight: "100vh",
    overflow: "hidden",
    background:
      "linear-gradient(145deg, #07111f 0%, #0b1729 48%, #101328 100%)",
    color: "#f8fafc",
    padding: "48px 32px 72px",
  },

  loading: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#07111f",
    color: "#cbd5e1",
    fontSize: "15px",
  },

  backgroundGlowOne: {
    position: "absolute",
    top: "-180px",
    right: "-130px",
    width: "520px",
    height: "520px",
    borderRadius: "50%",
    background:
      "radial-gradient(circle, rgba(126, 87, 255, 0.26) 0%, rgba(126, 87, 255, 0) 70%)",
    pointerEvents: "none",
  },

  backgroundGlowTwo: {
    position: "absolute",
    bottom: "-240px",
    left: "-180px",
    width: "620px",
    height: "620px",
    borderRadius: "50%",
    background:
      "radial-gradient(circle, rgba(41, 182, 246, 0.18) 0%, rgba(41, 182, 246, 0) 70%)",
    pointerEvents: "none",
  },

  container: {
    position: "relative",
    zIndex: 1,
    width: "100%",
    maxWidth: "1240px",
    margin: "0 auto",
  },

  hero: {
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "space-between",
    gap: "32px",
    marginBottom: "36px",
    padding: "12px 4px",
    flexWrap: "wrap",
  },

  eyebrow: {
    marginBottom: "14px",
    color: "#8b7cff",
    fontSize: "12px",
    fontWeight: 800,
    letterSpacing: "0.18em",
  },

  title: {
    margin: 0,
    fontSize: "clamp(36px, 5vw, 60px)",
    lineHeight: 1.12,
    letterSpacing: "-0.055em",
    fontWeight: 800,
  },

  subtitle: {
    margin: "20px 0 0",
    color: "#94a3b8",
    fontSize: "16px",
    lineHeight: 1.7,
  },

  primaryButton: {
    minWidth: "180px",
    height: "52px",
    padding: "0 22px",
    border: "1px solid rgba(255, 255, 255, 0.16)",
    borderRadius: "15px",
    background:
      "linear-gradient(135deg, #7657ff 0%, #986dff 52%, #bd75ff 100%)",
    boxShadow: "0 18px 42px rgba(118, 87, 255, 0.28)",
    color: "#ffffff",
    fontSize: "15px",
    fontWeight: 800,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "9px",
  },

  buttonSpark: {
    fontSize: "18px",
  },

  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
    gap: "18px",
    marginBottom: "22px",
  },

  statCard: {
    minHeight: "150px",
    padding: "24px",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "20px",
    background: "rgba(15, 27, 47, 0.74)",
    backdropFilter: "blur(18px)",
    boxShadow: "0 16px 46px rgba(0, 0, 0, 0.18)",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
  },

  statLabel: {
    color: "#94a3b8",
    fontSize: "13px",
    fontWeight: 700,
  },

  statNumber: {
    marginTop: "14px",
    color: "#ffffff",
    fontSize: "40px",
    lineHeight: 1,
    letterSpacing: "-0.04em",
  },

  planText: {
    marginTop: "14px",
    color: "#a99cff",
    fontSize: "28px",
    lineHeight: 1,
    letterSpacing: "-0.03em",
  },

  statDescription: {
    marginTop: "12px",
    color: "#64748b",
    fontSize: "12px",
  },

  contentGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.65fr) minmax(280px, 0.85fr)",
    gap: "22px",
    alignItems: "stretch",
  },

  panel: {
    minWidth: 0,
    padding: "26px",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "22px",
    background: "rgba(11, 23, 41, 0.82)",
    backdropFilter: "blur(20px)",
    boxShadow: "0 20px 52px rgba(0, 0, 0, 0.2)",
  },

  panelHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "16px",
    marginBottom: "22px",
  },

  sectionLabel: {
    display: "block",
    marginBottom: "6px",
    color: "#7467dc",
    fontSize: "10px",
    fontWeight: 800,
    letterSpacing: "0.15em",
  },

  panelTitle: {
    margin: 0,
    color: "#f8fafc",
    fontSize: "22px",
    letterSpacing: "-0.03em",
  },

  textButton: {
    padding: 0,
    border: 0,
    background: "transparent",
    color: "#9f92ff",
    fontSize: "13px",
    fontWeight: 700,
    cursor: "pointer",
  },

  recentGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
    gap: "16px",
  },

  adCard: {
    minWidth: 0,
    padding: 0,
    overflow: "hidden",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "16px",
    background: "rgba(255, 255, 255, 0.035)",
    textAlign: "left",
    cursor: "pointer",
  },

  imageWrap: {
    position: "relative",
    width: "100%",
    aspectRatio: "4 / 3",
    overflow: "hidden",
    background: "#111827",
  },

  image: {
    display: "block",
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },

  aiBadge: {
    position: "absolute",
    top: "10px",
    right: "10px",
    padding: "5px 8px",
    border: "1px solid rgba(255, 255, 255, 0.16)",
    borderRadius: "999px",
    background: "rgba(10, 17, 30, 0.72)",
    color: "#c4baff",
    fontSize: "10px",
    fontWeight: 800,
    backdropFilter: "blur(8px)",
  },

  adInfo: {
    display: "flex",
    flexDirection: "column",
    gap: "7px",
    padding: "15px",
  },

  adTitle: {
    overflow: "hidden",
    color: "#f8fafc",
    fontSize: "14px",
    lineHeight: 1.45,
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  adDate: {
    color: "#64748b",
    fontSize: "11px",
  },

  emptyState: {
    minHeight: "285px",
    border: "1px dashed rgba(255, 255, 255, 0.1)",
    borderRadius: "18px",
    background: "rgba(255, 255, 255, 0.02)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    padding: "30px",
  },

  emptyIcon: {
    width: "54px",
    height: "54px",
    marginBottom: "18px",
    borderRadius: "17px",
    background: "rgba(123, 97, 255, 0.12)",
    color: "#a99cff",
    fontSize: "25px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },

  emptyTitle: {
    margin: 0,
    color: "#f8fafc",
    fontSize: "18px",
  },

  emptyDescription: {
    margin: "10px 0 20px",
    color: "#64748b",
    fontSize: "13px",
  },

  emptyButton: {
    height: "40px",
    padding: "0 17px",
    border: "1px solid rgba(169, 156, 255, 0.3)",
    borderRadius: "11px",
    background: "rgba(123, 97, 255, 0.12)",
    color: "#bcb3ff",
    fontSize: "13px",
    fontWeight: 700,
    cursor: "pointer",
  },

  quickLinkList: {
    display: "flex",
    flexDirection: "column",
    gap: "11px",
  },

  quickLink: {
    width: "100%",
    minHeight: "76px",
    padding: "14px",
    border: "1px solid rgba(255, 255, 255, 0.065)",
    borderRadius: "15px",
    background: "rgba(255, 255, 255, 0.025)",
    color: "#f8fafc",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: "13px",
    textAlign: "left",
  },

  quickIcon: {
    flex: "0 0 auto",
    width: "42px",
    height: "42px",
    borderRadius: "13px",
    background: "rgba(123, 97, 255, 0.11)",
    color: "#a99cff",
    fontSize: "18px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },

  quickText: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "5px",
  },

  quickTitle: {
    color: "#f8fafc",
    fontSize: "14px",
  },

  quickDescription: {
    overflow: "hidden",
    color: "#64748b",
    fontSize: "11px",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  quickArrow: {
    flex: "0 0 auto",
    color: "#64748b",
    fontSize: "17px",
  },
};
