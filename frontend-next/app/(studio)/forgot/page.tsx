"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { EMAIL_PATTERN, apiFetch, readApiError, readJsonSafely } from "@/lib/api";
import { useStudio } from "@/components/studio/StudioProvider";
import { Brand } from "@/components/studio/chrome";

function ForgotContent() {
  const { toast } = useStudio();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<"username" | "password">(
    searchParams.get("mode") === "username" ? "username" : "password"
  );
  const [email, setEmail] = useState("");
  const [notice, setNotice] = useState<{ title: string; message: string } | null>(null);

  const findingUsername = mode === "username";

  function switchMode(next: "username" | "password") {
    setMode(next);
    setNotice(null);
  }

  async function submit() {
    const mail = email.trim();
    if (!mail) return toast("이메일을 입력해 주세요");
    if (!EMAIL_PATTERN.test(mail)) return toast("이메일 형식이 올바르지 않습니다");
    if (mode === "password") {
      setNotice({
        title: "메일을 보냈어요.",
        message:
          "받은 편지함에서 재설정 링크를 확인해 주세요. 몇 분 내로 도착합니다.",
      });
      toast("재설정 메일을 보냈어요");
      return;
    }
    try {
      const res = await apiFetch("/api/auth/find-username", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: mail }),
      });
      const data = (await readJsonSafely(res)) as { username?: string } | null;
      if (!res.ok) throw new Error(readApiError(data, "아이디를 찾지 못했습니다"));
      setNotice({ title: "가입된 아이디", message: data?.username || "" });
    } catch (err) {
      toast(err instanceof Error ? err.message : "아이디를 찾지 못했습니다");
    }
  }

  const modeBtn = (active: boolean): React.CSSProperties => ({
    padding: "8px 12px",
    border: `1px solid ${active ? "var(--gold)" : "var(--line)"}`,
    borderRadius: 8,
    background: active ? "var(--gold)" : "transparent",
    color: active ? "#16151A" : "var(--ink-soft)",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
  });

  return (
    <section className="auth-screen">
      <div className="login-left">
        <Link href="/login" className="back-link">
          ← 로그인으로
        </Link>
        <Brand large />
        <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
          <button type="button" style={modeBtn(findingUsername)} onClick={() => switchMode("username")}>
            아이디 찾기
          </button>
          <button type="button" style={modeBtn(!findingUsername)} onClick={() => switchMode("password")}>
            비밀번호 찾기
          </button>
        </div>
        <h1>
          {findingUsername ? (
            <>
              아이디를
              <br />
              잊으셨나요?
            </>
          ) : (
            <>
              비밀번호를
              <br />
              잊으셨나요?
            </>
          )}
        </h1>
        <p className="sub">
          {findingUsername ? (
            <>
              가입하신 이메일을 입력하시면
              <br />
              등록된 아이디를 확인할 수 있어요.
            </>
          ) : (
            <>
              가입하신 이메일을 입력하시면
              <br />
              비밀번호 재설정 링크를 보내드려요.
            </>
          )}
        </p>

        <div className={`notice${notice ? " on" : ""}`}>
          <span className="ck">✓</span>
          <span className="nt">
            <b>{notice?.title}</b>
            <br />
            <span>{notice?.message}</span>
          </span>
        </div>

        <div className="field">
          <label htmlFor="resetEmail">이메일</label>
          <input
            id="resetEmail"
            type="email"
            placeholder="you@store.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
        </div>
        <button className="btn-primary" onClick={submit}>
          {findingUsername ? "아이디 찾기" : "재설정 링크 받기"}
        </button>
        <p className="login-foot" style={{ marginTop: 22 }}>
          {findingUsername ? "아이디가 기억나셨나요?" : "비밀번호가 기억나셨나요?"}{" "}
          <Link href="/login">로그인</Link>
        </p>
      </div>

      <div className="login-right">
        <div className="spotlight" />
        <div className="showcase">
          <span className="tag">✦ 걱정 마세요</span>
          <div className="ad-preview">
            <div className="pic">
              <span className="badge">다시 시작</span>
              <div className="prod">☕</div>
            </div>
            <div className="cap">
              <h4>하루의 첫 여유</h4>
              <p>따뜻한 한 잔으로 다시 시작해요</p>
            </div>
          </div>
          <div className="float-copy">
            <span className="dot" /> 링크는 30분간 유효해요
          </div>
        </div>
      </div>
    </section>
  );
}

export default function ForgotPage() {
  return (
    <Suspense>
      <ForgotContent />
    </Suspense>
  );
}
