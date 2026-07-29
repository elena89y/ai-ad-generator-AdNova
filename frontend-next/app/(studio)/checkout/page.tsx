"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { BillingSummary, apiFetch, readApiError, readJsonSafely } from "@/lib/api";
import { useStudio } from "@/components/studio/StudioProvider";
import { Brand } from "@/components/studio/chrome";

function CheckoutContent() {
  const s = useStudio();
  const router = useRouter();
  const searchParams = useSearchParams();
  const changing = searchParams.get("mode") === "payment-method";
  const creditPack = searchParams.get("product");
  const buyingCreditPack = searchParams.get("mode") === "credit-pack";
  const creditPackLabel = creditPack === "credit_30" ? "크레딧 30개" : "크레딧 10개";
  const creditPackPrice = creditPack === "credit_30" ? "₩9,900" : "₩4,900";

  const [cardholder, setCardholder] = useState("");
  const [cardNumber, setCardNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvc, setCvc] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (s.ready && !s.token) {
      router.replace("/login");
      s.toast("로그인이 필요합니다");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.ready, s.token]);

  function formatCardNumber(v: string) {
    const digits = v.replace(/\D/g, "").slice(0, 16);
    setCardNumber(digits.replace(/(.{4})/g, "$1 ").trim());
  }
  function formatExpiry(v: string) {
    const digits = v.replace(/\D/g, "").slice(0, 4);
    setExpiry(digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits);
  }

  async function submit() {
    const digits = cardNumber.replace(/\D/g, "");
    if (!cardholder.trim()) return s.toast("카드 소유자 이름을 입력해주세요");
    if (!/^\d{16}$/.test(digits)) return s.toast("카드 번호 16자리를 확인해주세요");
    if (!/^(0[1-9]|1[0-2])\/(\d{2})$/.test(expiry))
      return s.toast("유효기간을 MM/YY 형식으로 입력해주세요");
    if (!/^\d{3,4}$/.test(cvc)) return s.toast("CVC 3~4자리를 확인해주세요");

    const endpoint = changing
      ? "/api/billing/demo/payment-method"
      : buyingCreditPack
        ? "/api/billing/demo/credit-packs"
        : "/api/billing/demo/subscribe";
    const cardBrand = digits.startsWith("4")
      ? "Visa"
      : digits.startsWith("5")
        ? "Mastercard"
        : "테스트카드";
    setBusy(true);
    try {
      const res = await apiFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          card_brand: cardBrand,
          card_last4: digits.slice(-4),
          ...(buyingCreditPack ? { product_id: creditPack || "credit_10" } : {}),
        }),
      });
      const data = (await readJsonSafely(res)) as BillingSummary | null;
      if (!res.ok) throw new Error(readApiError(data, "테스트 결제를 완료하지 못했습니다"));
      s.setBillingSummary(data);
      router.push("/billing");
      s.toast(
        changing
          ? "결제 방법을 변경했습니다"
          : buyingCreditPack
            ? `${creditPackLabel} 구매가 완료됐습니다`
            : "테스트 결제가 완료되어 프리미엄이 적용됐습니다"
      );
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "테스트 결제를 완료하지 못했습니다");
    } finally {
      setCardholder("");
      setCardNumber("");
      setExpiry("");
      setCvc("");
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="subbar">
        <Brand />
        <Link href="/billing" className="back-link" style={{ margin: "0 0 0 6px" }}>
          ← 구독 관리
        </Link>
      </div>
      <div className="page" style={{ maxWidth: 620 }}>
        <div style={{ margin: "6px 0 22px" }}>
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
            테스트 결제
          </span>
          <h2 style={{ fontSize: 24, fontWeight: 800, marginBottom: 7 }}>
            {changing ? "결제 방법 변경" : buyingCreditPack ? "크레딧 추가 구매" : "프리미엄 시작하기"}
          </h2>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", lineHeight: 1.6 }}>
            {changing
              ? "새 카드 정보를 확인하면 등록된 결제 방법이 변경됩니다."
              : buyingCreditPack
                ? "프리미엄 구독자만 구매할 수 있는 테스트 크레딧입니다."
                : "카드 정보를 확인하면 프리미엄 테스트 권한이 바로 적용됩니다."}
          </p>
        </div>
        <div className="set-card">
          {!changing && (
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 14,
                paddingBottom: 16,
                marginBottom: 18,
                borderBottom: "1px solid var(--line)",
              }}
            >
              <div>
                <div style={{ fontSize: 14, fontWeight: 800 }}>
                  {buyingCreditPack ? creditPackLabel : "프리미엄 월 구독"}
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-mute)", marginTop: 4 }}>
                  {buyingCreditPack ? "구매 후 광고 생성에 사용할 수 있어요" : "테스트 이용 기간 30일"}
                </div>
              </div>
              <b style={{ fontSize: 18, color: "var(--gold)" }}>
                {buyingCreditPack ? creditPackPrice : "₩9,900"}
              </b>
            </div>
          )}
          <div className="field">
            <label htmlFor="demoCardholder">카드 소유자 이름</label>
            <input
              id="demoCardholder"
              type="text"
              maxLength={40}
              autoComplete="off"
              placeholder="홍길동"
              value={cardholder}
              onChange={(e) => setCardholder(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="demoCardNumber">카드 번호</label>
            <input
              id="demoCardNumber"
              type="text"
              inputMode="numeric"
              maxLength={19}
              autoComplete="off"
              placeholder="0000 0000 0000 0000"
              value={cardNumber}
              onChange={(e) => formatCardNumber(e.target.value)}
            />
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))",
              gap: 12,
            }}
          >
            <div className="field">
              <label htmlFor="demoCardExpiry">유효기간</label>
              <input
                id="demoCardExpiry"
                type="text"
                inputMode="numeric"
                maxLength={5}
                autoComplete="off"
                placeholder="MM/YY"
                value={expiry}
                onChange={(e) => formatExpiry(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="demoCardCvc">CVC</label>
              <input
                id="demoCardCvc"
                type="password"
                inputMode="numeric"
                maxLength={4}
                autoComplete="off"
                placeholder="3~4자리"
                value={cvc}
                onChange={(e) => setCvc(e.target.value.replace(/\D/g, "").slice(0, 4))}
              />
            </div>
          </div>
          <p
            style={{
              fontSize: 11.5,
              color: "var(--ink-mute)",
              lineHeight: 1.65,
              margin: "2px 0 16px",
            }}
          >
            실제 결제는 발생하지 않습니다. 입력한 카드 번호, 유효기간, CVC는 서버로
            전송하거나 저장하지 않습니다.
          </p>
          <button
            className="btn-primary"
            style={{ width: "100%" }}
            disabled={busy}
            onClick={submit}
          >
            {changing ? "결제 방법 변경" : buyingCreditPack ? "크레딧 구매 완료" : "테스트 결제 완료"}
          </button>
        </div>
      </div>
    </section>
  );
}

export default function CheckoutPage() {
  return (
    <Suspense>
      <CheckoutContent />
    </Suspense>
  );
}
