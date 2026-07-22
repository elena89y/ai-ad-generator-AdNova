"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useEffect, type SyntheticEvent } from "react";

import {
  type AdnovaUser,
  EMAIL_PATTERN,
  PASSWORD_PATTERN,
  USERNAME_PATTERN,
  apiFetch,
  readApiError,
  readJsonSafely,
} from "@/lib/api";
import { useStudio } from "@/components/studio/StudioProvider";
import {
  Brand,
  InfoModal,
  PasswordInput,
} from "@/components/studio/chrome";

type OAuthProvider = "google" | "kakao" | "naver";

export default function SignupPage() {
  const { toast, setAuth } = useStudio();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [terms, setTerms] = useState(true);
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<"terms" | "privacy" | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [usernameError, setUsernameError] = useState<string | null>(null);
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState("");
  const [emailVerified, setEmailVerified] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    const mail = email.trim();
    if (!mail || !EMAIL_PATTERN.test(mail)) {
      setEmailError(null);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await apiFetch(
          `/api/auth/check-email?email=${encodeURIComponent(mail)}`
        );
        const data = (await readJsonSafely(res)) as { available?: boolean } | null;

        if (res.ok && data?.available === false) {
          setEmailError("이미 사용 중인 이메일입니다");
        } else {
          setEmailError(null);
        }
      } catch {
        // 네트워크 오류는 무시, 제출 시 서버에서 다시 검증됨
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [email]);

  useEffect(() => {
    const name = username.trim();
    if (!name || !USERNAME_PATTERN.test(name)) {
      setUsernameError(null);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await apiFetch(
          `/api/auth/check-username?username=${encodeURIComponent(name)}`
        );
        const data = (await readJsonSafely(res)) as { available?: boolean } | null;

        if (res.ok && data?.available === false) {
          setUsernameError("이미 사용 중인 아이디입니다");
        } else {
          setUsernameError(null);
        }
      } catch {
        // ignore
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [username]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function handleSendCode() {
    const mail = email.trim();
    if (!EMAIL_PATTERN.test(mail)) {
      toast("이메일 형식이 올바르지 않습니다");
      return;
    }
    const res = await apiFetch("/api/auth/send-verification-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: mail }),
    });
    const data = await readJsonSafely(res);
    if (!res.ok) {
      toast(readApiError(data, "인증번호 발송에 실패했습니다"));
      return;
    }
    setCodeSent(true);
    setCooldown(60);
    toast("인증번호가 발송되었습니다");
  }


  async function handleVerifyCode() {
    const res = await apiFetch("/api/auth/verify-email-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), code: code.trim() }),
    });
    const data = await readJsonSafely(res);
    if (!res.ok) {
      toast(readApiError(data, "인증에 실패했습니다"));
      return;
    }
    setEmailVerified(true);
    toast("이메일 인증이 완료되었습니다");
  }


  function startOAuth(provider: OAuthProvider) {
    window.location.href = `/api/auth/${provider}/login`;
  }

  async function handleSignup(
    event: SyntheticEvent<HTMLFormElement>
  ): Promise<void> {
    event.preventDefault();

    const mail = email.trim();
    const name = username.trim();
    const storeName = businessName.trim();

    if (!mail) {
      toast("이메일을 입력해 주세요");
      return;
    }

    if (!EMAIL_PATTERN.test(mail)) {
      toast("이메일 형식이 올바르지 않습니다");
      return;
    }

    if (!name) {
      toast("아이디를 입력해 주세요");
      return;
    }

    if (!USERNAME_PATTERN.test(name)) {
      toast("아이디는 영문과 숫자만 사용해서 7~12자로 입력해 주세요");
      return;
    }

    if (!password) {
      toast("비밀번호를 입력해 주세요");
      return;
    }

    if (!PASSWORD_PATTERN.test(password)) {
      toast(
        "비밀번호는 8~20자이며 대문자, 소문자, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다"
      );
      return;
    }

    if (password !== passwordConfirm) {
      toast("비밀번호가 서로 다릅니다");
      return;
    }

    if (emailError || usernameError) {
      toast("입력하신 정보를 다시 확인해 주세요");
      return;
    }

    if (!emailVerified) {
      toast("이메일 인증을 완료해 주세요");
      return;
    }

    if (!terms) {
      toast("이용약관 및 개인정보처리방침에 동의해 주세요");
      return;
    }

    setBusy(true);

    try {
      /*
       * 1. 회원가입
       * signup 엔드포인트는 JSON 요청
       */
      const signupResponse = await apiFetch("/api/auth/signup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: mail,
          username: name,
          password,
          business_name: storeName || null,
        }),
      });

      const signupData = await readJsonSafely(signupResponse);

      if (!signupResponse.ok) {
        throw new Error(
          readApiError(signupData, "회원가입에 실패했습니다")
        );
      }

      /*
       * 2. 회원가입 직후 자동 로그인
       * FastAPI 로그인은 JSON 요청
       */
      const loginResponse = await apiFetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: name,
          password,
        }),
      });

      const loginData = (await readJsonSafely(loginResponse)) as {
        access_token?: string;
        user?: AdnovaUser;
      } | null;

      if (
        !loginResponse.ok ||
        !loginData?.access_token ||
        !loginData.user
      ) {
        throw new Error(
          readApiError(
            loginData,
            "회원가입은 완료됐지만 자동 로그인에 실패했습니다"
          )
        );
      }

      setAuth(loginData.access_token, loginData.user);
      toast("회원가입이 완료되었습니다");
      router.push("/onboarding");
    } catch (error) {
      toast(
        error instanceof Error
          ? error.message
          : "회원가입에 실패했습니다"
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth-screen">
      <div className="login-left">
        <Link href="/login" className="back-link">
          ← 로그인으로
        </Link>

        <Brand large />

        <h1>무료로 시작하기</h1>

        <p className="sub">
          가입하고 첫 광고를 만들어보세요.
          <br />
          무료 크레딧으로 바로 시작할 수 있어요.
        </p>

        <form onSubmit={handleSignup}>

          <div className="field">
            <label htmlFor="signupEmail">이메일</label>

            <div style={{ display: "flex", gap: 8 }}>
              <input
                id="signupEmail"
                type="email"
                placeholder="you@store.com"
                autoComplete="email"
                value={email}
                disabled={busy || emailVerified}
                onChange={(event) => setEmail(event.target.value)}
                style={{ flex: 1 }}
              />
              <button
                type="button"
                className={emailVerified ? "btn-secondary verified" : "btn-secondary"}
                disabled={busy || emailVerified || cooldown > 0 || !!emailError}
                onClick={handleSendCode}
              >
                {emailVerified
                  ? "인증완료"
                  : cooldown > 0
                    ? `재발송 (${cooldown}s)`
                    : codeSent
                      ? "재발송"
                      : "인증번호 발송"}
              </button>
            </div>

            {emailError && (
              <div
                className="field-error"
                style={{ color: "#e5484d", fontSize: 12, marginTop: 4 }}
              >
                {emailError}
              </div>
            )}

            {codeSent && !emailVerified && (
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="인증번호 6자리"
                  value={code}
                  disabled={busy}
                  onChange={(event) => setCode(event.target.value)}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={busy || code.length !== 6}
                  onClick={handleVerifyCode}
                >
                  확인
                </button>
              </div>
            )}
          </div>

          <div className="field">
            <label htmlFor="signupUsername">아이디</label>

            <input
              id="signupUsername"
              type="text"
              placeholder="영문/숫자 7~12자"
              autoComplete="username"
              value={username}
              disabled={busy}
              onChange={(event) => setUsername(event.target.value)}
            />

            {usernameError && (
              <div
                className="field-error"
                style={{ color: "#e5484d", fontSize: 12, marginTop: 4 }}
              >
                {usernameError}
              </div>
            )}
          </div>

          <div className="field">
            <label htmlFor="signupBusinessName">
              가게 / 상호명{" "}
              <span
                style={{
                  fontWeight: 500,
                  color: "var(--ink-mute)",
                }}
              >
                (선택)
              </span>
            </label>

            <input
              id="signupBusinessName"
              type="text"
              placeholder="예: 아드노바 카페"
              autoComplete="organization"
              value={businessName}
              disabled={busy}
              onChange={(event) => setBusinessName(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="signupPassword">비밀번호</label>

            <PasswordInput
              id="signupPassword"
              placeholder="8~20자, 대소문자·숫자·특수문자 포함"
              autoComplete="new-password"
              value={password}
              disabled={busy}
              onChange={(event) => setPassword(event.target.value)}
            />

            <div className="field-help">
              8~20자이며 대문자, 소문자, 숫자, 특수문자를 각각
              1개 이상 포함해야 합니다.
            </div>
          </div>

          <div className="field">
            <label htmlFor="signupPasswordConfirm">
              비밀번호 확인
            </label>

            <PasswordInput
              id="signupPasswordConfirm"
              placeholder="비밀번호를 다시 입력해 주세요"
              autoComplete="new-password"
              value={passwordConfirm}
              disabled={busy}
              onChange={(event) =>
                setPasswordConfirm(event.target.value)
              }
            />
          </div>

          <label className="terms">
            <input
              type="checkbox"
              checked={terms}
              disabled={busy}
              onChange={(event) => setTerms(event.target.checked)}
              style={{ marginTop: 3 }}
            />

            <span>
              <button
                type="button"
                className="terms-link"
                onClick={() => setModal("terms")}
              >
                이용약관
              </button>{" "}
              및{" "}
              <button
                type="button"
                className="terms-link"
                onClick={() => setModal("privacy")}
              >
                개인정보처리방침
              </button>
              에 동의합니다.
            </span>
          </label>

          <button
            className="btn-primary"
            type="submit"
            disabled={busy}
          >
            {busy ? "가입하는 중..." : "무료로 시작하기"}
          </button>
        </form>

        <div className="divider">또는</div>

        <div className="socials compact">
          <button
            className="soc"
            type="button"
            disabled={busy}
            onClick={() => startOAuth("google")}
          >
            <span className="ic social-icon-white">
              <Image
                src="/assets/icons/google.svg"
                alt=""
                width={18}
                height={18}
              />
            </span>
            Google
          </button>

          <button
            className="soc"
            type="button"
            disabled={busy}
            onClick={() => startOAuth("kakao")}
          >
            <span className="ic social-icon-kakao">
              <Image
                src="/assets/icons/kakao.png"
                alt=""
                width={18}
                height={18}
              />
            </span>
            카카오
          </button>

          <button
            className="soc"
            type="button"
            disabled={busy}
            onClick={() => startOAuth("naver")}
          >
            <span className="ic social-icon-naver">
              <Image
                src="/assets/icons/naver.png"
                alt=""
                width={18}
                height={18}
              />
            </span>
            네이버
          </button>
        </div>

        <p className="login-foot">
          이미 계정이 있으세요? <Link href="/login">로그인</Link>
        </p>
      </div>

      <div className="login-right">

        <div className="showcase">
          <span className="tag">✦ 가입하면 바로</span>

          <div className="ad-preview">
            <div className="pic">
              <span className="badge">첫 광고 무료</span>
              <div className="prod">🍞</div>
            </div>

            <div className="cap">
              <h4>갓 구운 아침을 팝니다</h4>
              <p>오늘 구운 빵, 오후 2시 타임세일</p>
            </div>
          </div>

          <div className="float-copy">
            <span className="dot" /> 무료 크레딧 제공
          </div>
        </div>
      </div>

      <InfoModal
        open={modal === "terms"}
        onClose={() => setModal(null)}
        title="이용약관"
      >
        <p>
          <b>제1조 (목적)</b>
          <br />
          본 약관은 AdNova(이하 &quot;서비스&quot;)가 제공하는
          AI 광고 생성 서비스의 이용 조건 및 절차에 관한 사항을
          규정합니다.
        </p>

        <br />

        <p>
          <b>제2조 (서비스 이용)</b>
          <br />
          서비스는 소상공인을 대상으로 AI 기반 광고 이미지 및
          문구 생성 기능을 제공합니다. 생성된 광고물의 이용
          권한은 관련 법령과 서비스 정책에 따릅니다.
        </p>

        <br />

        <p>
          <b>제3조 (크레딧 및 결제)</b>
          <br />
          무료 체험 크레딧은 가입 시 제공되며, 유료 플랜의
          크레딧 수량과 이용 조건은 결제 화면에 고지됩니다.
        </p>

        <br />

        <p>
          <b>제4조 (서비스 중단)</b>
          <br />
          서비스는 시스템 점검이나 장애 등의 사유로 일시
          중단될 수 있으며, 필요한 경우 사전에 공지합니다.
        </p>
      </InfoModal>

      <InfoModal
        open={modal === "privacy"}
        onClose={() => setModal(null)}
        title="개인정보처리방침"
      >
        <p>
          <b>수집하는 개인정보</b>
          <br />
          이메일 주소, 아이디, 상호명, 서비스 이용 과정에서
          업로드한 제품 이미지
        </p>

        <br />

        <p>
          <b>수집 목적</b>
          <br />
          회원 가입 및 로그인, 서비스 제공, 광고 생성 결과 및
          이용 이력 관리
        </p>

        <br />

        <p>
          <b>보유 기간</b>
          <br />
          회원 탈퇴 시까지 보유하며, 법령상 보존 의무가 있는
          경우 해당 기간 동안 보관합니다.
        </p>

        <br />

        <p>
          <b>제3자 제공</b>
          <br />
          법령에 따른 경우를 제외하고 이용자의 동의 없이
          개인정보를 제3자에게 제공하지 않습니다.
        </p>
      </InfoModal>
    </section>
  );
}
