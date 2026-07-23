"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BillingSummary,
  apiFetch,
  formatBillingAmount,
  formatBillingDate,
  readApiError,
  readJsonSafely,
} from "@/lib/api";
import { useStudio } from "@/components/studio/StudioProvider";
import { SubBar } from "@/components/studio/chrome";

export default function BillingPage() {
  const s = useStudio();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (s.ready && !s.token) router.replace("/login");
  }, [s.ready, s.token, router]);

  useEffect(() => {
    s.refreshBilling(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const summary = s.billingSummary;
  const subscription = summary?.subscription;
  const paymentMethod = summary?.payment_method;
  const bonusCredits = summary?.bonus_credits_remaining ?? 0;
  const purchasedCredits = summary?.purchased_credits_remaining ?? 0;
  const isPremium = s.isPremium;
  const cancelPending = Boolean(subscription?.cancel_at_period_end);
  const hasBillingData = Boolean(
    subscription || paymentMethod || s.billingPurchases.length
  );

  async function toggleCancellation() {
    if (!subscription) return;
    if (
      !cancelPending &&
      !confirm(`${formatBillingDate(subscription.current_period_end)}에 구독을 해지할까요?`)
    )
      return;
    setBusy(true);
    try {
      const endpoint = cancelPending
        ? "/api/billing/subscription/resume"
        : "/api/billing/subscription/cancel";
      const res = await apiFetch(endpoint, { method: "POST" });
      const data = (await readJsonSafely(res)) as BillingSummary | null;
      if (!res.ok) throw new Error(readApiError(data, "구독 상태를 변경하지 못했습니다"));
      s.setBillingSummary(data);
      s.toast(cancelPending ? "해지 예약을 취소했습니다" : "구독 해지를 예약했습니다");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "구독 상태를 변경하지 못했습니다");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <SubBar
        backHref="/studio"
        backLabel="뒤로"
        right={
          <span className="credits">
            {isPremium ? (
              <>
                크레딧 <b>{s.premiumLeft}/{s.premiumTotal}</b>
              </>
            ) : (
              <>
                크레딧 <b>{s.freeLeft}</b>
              </>
            )}
            {bonusCredits > 0 && <> · 보너스 <b>{bonusCredits}</b></>}
            {purchasedCredits > 0 && <> · 구매 <b>{purchasedCredits}</b></>}
          </span>
        }
      />
      <div className="page" style={{ maxWidth: 720 }}>
        {!isPremium && (
          <div>
            <div style={{ textAlign: "center", margin: "6px 0 22px" }}>
              <span
                style={{
                  display: "inline-block",
                  fontSize: 11,
                  fontWeight: 800,
                  color: "var(--gold)",
                  background: "rgba(242,169,59,.14)",
                  padding: "5px 12px",
                  borderRadius: 999,
                  marginBottom: 10,
                }}
              >
                ✦ 업그레이드
              </span>
              <h2
                style={{
                  fontSize: 22,
                  fontWeight: 800,
                  letterSpacing: "-.5px",
                  marginBottom: 6,
                }}
              >
                워터마크 없이, 고해상도 원본으로
              </h2>
              <p style={{ fontSize: 13, color: "var(--ink-mute)" }}>
                무료 체험 3회 이후에는 크레딧으로 광고를 만들 수 있어요.
              </p>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 14,
                marginBottom: 18,
              }}
            >
              <div
                style={{
                  background: "var(--card)",
                  border: "1px solid rgba(255,255,255,.1)",
                  borderRadius: 16,
                  padding: 20,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink-soft)" }}>
                  무료 체험
                </div>
                <div
                  style={{
                    fontSize: 26,
                    fontWeight: 800,
                    letterSpacing: -1,
                    margin: "6px 0 14px",
                  }}
                >
                  ₩0
                </div>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 9,
                    fontSize: 12.5,
                    color: "var(--ink-soft)",
                  }}
                >
                  <div>
                    ✓ 가입 시 <b style={{ color: "var(--ink)" }}>크레딧 3개</b>
                  </div>
                  <div style={{ color: "var(--ink-mute)" }}>· 광고 생성마다 1개 차감</div>
                  <div style={{ color: "var(--ink-mute)" }}>· 미리보기 · 로고 워터마크</div>
                  <div style={{ color: "var(--ink-mute)" }}>· 이력 저장 (다운로드 X)</div>
                </div>
                <button
                  style={{
                    width: "100%",
                    marginTop: 16,
                    padding: 11,
                    border: "1px solid rgba(255,255,255,.12)",
                    borderRadius: 11,
                    background: "rgba(255,255,255,.04)",
                    color: "var(--ink-mute)",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: "default",
                  }}
                >
                  현재 플랜
                </button>
              </div>
              <div
                style={{
                  background: "linear-gradient(160deg,#26222b,#1F1E25)",
                  border: "1.5px solid var(--gold)",
                  borderRadius: 16,
                  padding: 20,
                  position: "relative",
                  boxShadow: "0 0 0 3px rgba(242,169,59,.12)",
                }}
              >
                <span
                  style={{
                    position: "absolute",
                    top: -11,
                    right: 16,
                    background: "var(--gold)",
                    color: "#16151A",
                    fontSize: 11,
                    fontWeight: 800,
                    padding: "4px 10px",
                    borderRadius: 7,
                  }}
                >
                  추천
                </span>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--gold-deep)" }}>
                  프리미엄
                </div>
                <div
                  style={{
                    fontSize: 26,
                    fontWeight: 800,
                    letterSpacing: -1,
                    margin: "6px 0 14px",
                  }}
                >
                  ₩9,900
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-mute)" }}>
                    /월
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 9,
                    fontSize: 12.5,
                    color: "var(--ink-soft)",
                  }}
                >
                  <div>
                    ✓ 매월 <b style={{ color: "var(--ink)" }}>크레딧 30개</b>
                  </div>
                  <div>
                    ✓ <b style={{ color: "var(--ink)" }}>워터마크 없음</b>
                  </div>
                  <div>✓ 고해상도 원본 다운로드</div>
                  <div>✓ 크레딧 추가 구매 가능</div>
                </div>
                <button
                  style={{
                    width: "100%",
                    marginTop: 16,
                    padding: 11,
                    border: "none",
                    borderRadius: 11,
                    background: "var(--gold)",
                    color: "#16151A",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                  onClick={() => router.push("/checkout")}
                >
                  프리미엄 시작하기
                </button>
              </div>
            </div>
            <p
              style={{
                margin: "12px 2px 0",
                fontSize: 11.5,
                color: "#6b6775",
                textAlign: "center",
              }}
            >
              ※ 현재는 실제 청구 없이 결제 버튼을 누르면 프리미엄이 적용되는 테스트
              방식입니다.
            </p>
          </div>
        )}

        {(isPremium || hasBillingData) && (
          <div style={{ marginTop: isPremium ? 0 : 30 }}>
            <div
              style={{ display: "flex", alignItems: "center", gap: 10, margin: "6px 0 20px" }}
            >
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 800,
                  color: "#16151A",
                  background: "var(--gold)",
                  padding: "5px 12px",
                  borderRadius: 999,
                }}
              >
                {isPremium
                  ? cancelPending
                    ? "해지 예정"
                    : "✦ 프리미엄 이용 중"
                  : "구독 종료"}
              </span>
              <h2 style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-.5px" }}>
                구독 관리
              </h2>
            </div>
            <div className="set-card">
              <h4>구독 정보</h4>
              <div
                style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13 }}
              >
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--ink-mute)" }}>플랜</span>
                  <b>
                    {subscription?.plan === "premium"
                      ? "프리미엄"
                      : subscription?.plan || "무료"}
                  </b>
                </div>
                {isPremium && (
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--ink-mute)" }}>이번 달 남은 생성</span>
                    <b>{s.premiumLeft}/{s.premiumTotal}회</b>
                  </div>
                )}
                {bonusCredits > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--ink-mute)" }}>보너스 크레딧</span>
                    <b>{bonusCredits}개</b>
                  </div>
                )}
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--ink-mute)" }}>구매 크레딧</span>
                  <b>{purchasedCredits}개</b>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--ink-mute)" }}>
                    {cancelPending || subscription?.status !== "active"
                      ? "이용 종료일"
                      : "다음 결제일"}
                  </span>
                  <span>{formatBillingDate(subscription?.current_period_end)}</span>
                </div>
                {cancelPending && (
                  <p style={{ color: "var(--berry)", fontSize: 12, lineHeight: 1.6 }}>
                    {formatBillingDate(subscription?.current_period_end)}까지 프리미엄
                    기능을 이용할 수 있습니다.
                  </p>
                )}
              </div>
            </div>
            <div className="set-card">
              <h4>크레딧 추가 구매</h4>
              <p style={{ fontSize: 12, color: "var(--ink-mute)", margin: "-3px 0 14px" }}>
                월 크레딧을 모두 사용한 뒤 구매 크레딧이 사용됩니다.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 10 }}>
                <button
                  type="button"
                  style={{ padding: 14, border: "1px solid var(--line)", borderRadius: 11, background: "rgba(255,255,255,.04)", color: "var(--ink)", textAlign: "left", cursor: "pointer" }}
                  onClick={() => router.push("/checkout?mode=credit-pack&product=credit_10")}
                >
                  <b>크레딧 10개</b><br /><span style={{ color: "var(--gold)", fontWeight: 800 }}>₩4,900</span>
                </button>
                <button
                  type="button"
                  style={{ padding: 14, border: "1px solid var(--gold)", borderRadius: 11, background: "rgba(242,169,59,.08)", color: "var(--ink)", textAlign: "left", cursor: "pointer" }}
                  onClick={() => router.push("/checkout?mode=credit-pack&product=credit_30")}
                >
                  <b>크레딧 30개</b><br /><span style={{ color: "var(--gold)", fontWeight: 800 }}>₩9,900</span>
                </button>
              </div>
            </div>
            <div className="set-card">
              <h4>결제 내역</h4>
              {s.billingPurchases.length === 0 ? (
                <div style={{ fontSize: 13, color: "var(--ink-mute)" }}>
                  아직 결제 내역이 없습니다.
                </div>
              ) : (
                s.billingPurchases.map((p, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 14,
                      padding: "10px 0",
                      fontSize: 13,
                      borderBottom:
                        i < s.billingPurchases.length - 1 ? "1px solid var(--line)" : "none",
                    }}
                  >
                    <span>
                      {formatBillingDate(p.purchased_at)} · {p.description}
                      {p.status === "paid" ? "" : ` · ${p.status}`}
                    </span>
                    <b>{formatBillingAmount(p.amount, p.currency)}</b>
                  </div>
                ))
              )}
            </div>
            <div className="set-card">
              <h4>결제 방법</h4>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>
                  {paymentMethod
                    ? `💳 ${paymentMethod.card_brand || "카드"} •••• ${paymentMethod.card_last4 || "----"}`
                    : "등록된 결제 방법이 없습니다."}
                </span>
                <button
                  style={{
                    marginLeft: "auto",
                    padding: "9px 14px",
                    border: "1px solid rgba(255,255,255,.14)",
                    borderRadius: 10,
                    background: "transparent",
                    color: "var(--ink-soft)",
                    fontSize: 12.5,
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                  onClick={() => router.push("/checkout?mode=payment-method")}
                >
                  변경
                </button>
              </div>
            </div>
            {isPremium && (
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button
                  disabled={busy}
                  style={{
                    padding: "12px 18px",
                    border: "1px solid rgba(224,86,127,.4)",
                    borderRadius: 11,
                    background: "transparent",
                    color: "var(--berry)",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                  onClick={toggleCancellation}
                >
                  {cancelPending ? "해지 예약 취소" : "구독 해지"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
