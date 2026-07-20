"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  PASSWORD_PATTERN,
  apiFetch,
  avatarHue,
  clearAvatarPhoto,
  getDisplayName,
  getStoredAvatarPhoto,
  isSocialAuthUser,
  readApiError,
  readJsonSafely,
  storeAvatarPhoto,
} from "@/lib/api";
import { useHydrated, useStudio } from "@/components/studio/StudioProvider";
import { SubBar } from "@/components/studio/chrome";

export default function SettingsPage() {
  const s = useStudio();
  const router = useRouter();
  const hydrated = useHydrated();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [notiState, setNotiState] = useState([true, true, false]);
  const [avatarOverride, setAvatarOverride] = useState<string | null>(null);
  const avatarFileRef = useRef<HTMLInputElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const pwRef = useRef<HTMLDivElement>(null);
  const notiRef = useRef<HTMLDivElement>(null);
  const deleteRef = useRef<HTMLDivElement>(null);
  const [activeNav, setActiveNav] = useState("setProfile");

  const social = hydrated ? isSocialAuthUser() : false;
  const avatarPhoto = avatarOverride ?? (hydrated ? getStoredAvatarPhoto() : "");

  useEffect(() => {
    if (s.ready && !s.token) router.replace("/login");
  }, [s.ready, s.token, router]);

  const name = getDisplayName(s.user);
  const hue = avatarHue(name);

  function scrollToSection(
    id: string,
    ref: React.RefObject<HTMLDivElement | null>
  ) {
    setActiveNav(id);
    const el = ref.current;
    if (el)
      window.scrollTo({
        top: el.getBoundingClientRect().top + window.scrollY - 90,
        behavior: "smooth",
      });
  }

  function handleAvatarUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      storeAvatarPhoto(reader.result as string);
      setAvatarOverride(reader.result as string);
      s.bumpUser();
      s.toast("프로필 사진이 변경되었습니다");
    };
    reader.readAsDataURL(file);
  }

  async function handlePasswordChange() {
    if (social)
      return s.toast("소셜 로그인 계정의 비밀번호는 해당 서비스에서 관리됩니다");
    if (!currentPassword) return s.toast("현재 비밀번호를 입력해주세요");
    if (!PASSWORD_PATTERN.test(newPassword))
      return s.toast(
        "새 비밀번호는 8~20자이며 대문자, 소문자, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다"
      );
    if (newPassword !== newPasswordConfirm) return s.toast("새 비밀번호가 서로 다릅니다");

    setBusy(true);
    try {
      const res = await apiFetch("/api/account/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      const data = await readJsonSafely(res);
      if (!res.ok) throw new Error(readApiError(data, "비밀번호를 변경하지 못했습니다"));
      setCurrentPassword("");
      setNewPassword("");
      setNewPasswordConfirm("");
      s.clearAuth();
      router.push("/login");
      s.toast("비밀번호가 변경되었습니다. 새 비밀번호로 다시 로그인해주세요");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "비밀번호를 변경하지 못했습니다");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteAccount() {
    if (!social && !deletePassword) return s.toast("현재 비밀번호를 입력해주세요");
    if (!confirm("정말 회원 탈퇴할까요? 계정과 모든 광고 데이터가 삭제되며 복구할 수 없습니다."))
      return;
    setBusy(true);
    try {
      const res = await apiFetch("/api/account", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(social ? {} : { current_password: deletePassword }),
      });
      if (!res.ok) {
        const data = await readJsonSafely(res);
        throw new Error(readApiError(data, "회원 탈퇴에 실패했습니다"));
      }
      s.clearAuth();
      clearAvatarPhoto();
      router.push("/login");
      s.toast("회원 탈퇴가 완료되었습니다");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "회원 탈퇴에 실패했습니다");
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    s.clearAuth();
    router.push("/login");
    s.toast("로그아웃되었습니다");
  }

  const noti = ["광고 생성 완료 이메일", "크레딧 소진 알림", "마케팅 소식 받기"];

  return (
    <section>
      <SubBar backHref="/studio" backLabel="대시보드" />
      <div className="page">
        <div className="page-head">
          <div>
            <h2>계정 설정</h2>
            <p className="lead">프로필과 보안, 알림 설정을 관리하세요.</p>
          </div>
        </div>
        <div className="set-grid">
          <div className="set-nav">
            <button
              className={`set-nav-item${activeNav === "setProfile" ? " on" : ""}`}
              onClick={() => scrollToSection("setProfile", profileRef)}
            >
              프로필
            </button>
            <button
              className={`set-nav-item${activeNav === "setPw" ? " on" : ""}`}
              onClick={() => scrollToSection("setPw", pwRef)}
            >
              비밀번호
            </button>
            <button
              className={`set-nav-item${activeNav === "setNoti" ? " on" : ""}`}
              onClick={() => scrollToSection("setNoti", notiRef)}
            >
              알림
            </button>
            <button className="set-nav-item" onClick={() => router.push("/billing")}>
              플랜 &amp; 결제
            </button>
            <div className="pf-div" style={{ margin: "8px 4px" }} />
            <button
              className="set-nav-item"
              style={{ color: "var(--berry)" }}
              onClick={handleLogout}
            >
              로그아웃
            </button>
            <button
              className="set-nav-item"
              style={{ color: "var(--ink-mute)" }}
              onClick={() => scrollToSection("setDelete", deleteRef)}
            >
              회원 탈퇴
            </button>
          </div>
          <div>
            <div className="set-card" ref={profileRef}>
              <h4>프로필</h4>
              <div
                style={{
                  display: "flex",
                  gap: 14,
                  alignItems: "center",
                  marginBottom: 16,
                }}
              >
                <div
                  className="av-lg"
                  style={{
                    width: 56,
                    height: 56,
                    fontSize: 20,
                    ...(avatarPhoto
                      ? { backgroundImage: `url("${avatarPhoto}")`, color: "transparent" }
                      : {
                          background: `linear-gradient(135deg,hsl(${hue} 48% 42%),hsl(${(hue + 42) % 360} 58% 56%))`,
                        }),
                  }}
                >
                  {avatarPhoto ? "" : (name || "A").trim().charAt(0).toUpperCase()}
                </div>
                <button
                  style={{
                    padding: "8px 14px",
                    border: "1px solid rgba(255,255,255,.14)",
                    borderRadius: 9,
                    background: "transparent",
                    color: "var(--ink-soft)",
                    fontSize: 12.5,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                  onClick={() => avatarFileRef.current?.click()}
                >
                  사진 변경
                </button>
                <input
                  ref={avatarFileRef}
                  type="file"
                  accept="image/*"
                  style={{ display: "none" }}
                  onChange={handleAvatarUpload}
                />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <div className="fl">가게 / 상호명</div>
                  <div className="mini-in">
                    {s.user?.business_name || s.user?.name || "정보 없음"}
                  </div>
                </div>
                <div>
                  <div className="fl">아이디</div>
                  <div className="mini-in">{s.user?.username || "정보 없음"}</div>
                </div>
                <div style={{ gridColumn: "1/3" }}>
                  <div className="fl">이메일</div>
                  <div className="mini-in">{s.user?.email || "정보 없음"}</div>
                </div>
              </div>
            </div>

            <div className="set-card" ref={pwRef}>
              <h4>비밀번호 변경</h4>
              {social ? (
                <p style={{ fontSize: 12.5, lineHeight: 1.65, color: "var(--ink-mute)" }}>
                  소셜 로그인 계정의 비밀번호는 Google, Kakao 또는 Naver에서 관리합니다.
                </p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <input
                    className="mini-in"
                    type="password"
                    autoComplete="current-password"
                    placeholder="현재 비밀번호"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                  />
                  <input
                    className="mini-in"
                    type="password"
                    autoComplete="new-password"
                    placeholder="새 비밀번호 입력 · 8~20자, 대소문자·숫자·특수문자 포함"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                  />
                  <input
                    className="mini-in"
                    type="password"
                    autoComplete="new-password"
                    placeholder="새 비밀번호 확인"
                    value={newPasswordConfirm}
                    onChange={(e) => setNewPasswordConfirm(e.target.value)}
                  />
                  <button
                    disabled={busy}
                    style={{
                      alignSelf: "flex-end",
                      padding: "10px 16px",
                      border: "none",
                      borderRadius: 10,
                      background: "var(--gold)",
                      color: "#16151A",
                      fontSize: 12.5,
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                    onClick={handlePasswordChange}
                  >
                    비밀번호 변경
                  </button>
                </div>
              )}
            </div>

            <div className="set-card" ref={notiRef}>
              <h4>알림</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
                {noti.map((label, i) => (
                  <div
                    key={label}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <span style={{ fontSize: 13, color: "var(--ink-soft)" }}>{label}</span>
                    <span
                      className={`toggle ${notiState[i] ? "on" : "off"}`}
                      onClick={() =>
                        setNotiState((prev) => prev.map((v, j) => (j === i ? !v : v)))
                      }
                    >
                      <span className="k" />
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div
              className="set-card"
              ref={deleteRef}
              style={{ borderColor: "rgba(224,86,127,.35)" }}
            >
              <h4 style={{ color: "var(--berry)" }}>회원 탈퇴</h4>
              <p
                style={{
                  fontSize: 12.5,
                  lineHeight: 1.65,
                  color: "var(--ink-mute)",
                  marginBottom: 12,
                }}
              >
                탈퇴하면 계정과 광고 이력, 업로드 이미지, 생성 이미지, 결제 내역이 모두
                삭제되며 복구할 수 없습니다.
              </p>
              {social && (
                <p
                  style={{
                    fontSize: 12.5,
                    lineHeight: 1.65,
                    color: "var(--ink-mute)",
                    marginBottom: 12,
                  }}
                >
                  소셜 로그인 계정은 비밀번호 확인 없이 탈퇴할 수 있습니다.
                </p>
              )}
              <div
                style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}
              >
                {!social && (
                  <input
                    className="mini-in"
                    type="password"
                    autoComplete="current-password"
                    placeholder="현재 비밀번호"
                    style={{ flex: 1, minWidth: 220, width: "auto" }}
                    value={deletePassword}
                    onChange={(e) => setDeletePassword(e.target.value)}
                  />
                )}
                <button
                  disabled={busy}
                  style={{
                    padding: "10px 16px",
                    border: "1px solid rgba(224,86,127,.45)",
                    borderRadius: 10,
                    background: "transparent",
                    color: "var(--berry)",
                    fontSize: 12.5,
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                  onClick={handleDeleteAccount}
                >
                  회원 탈퇴
                </button>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button
                style={{
                  padding: "12px 18px",
                  border: "1px solid rgba(255,255,255,.14)",
                  borderRadius: 11,
                  background: "transparent",
                  color: "var(--ink-soft)",
                  fontSize: 13.5,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
                onClick={() => router.push("/studio")}
              >
                취소
              </button>
              <button
                style={{
                  padding: "12px 20px",
                  border: "none",
                  borderRadius: 11,
                  background: "var(--gold)",
                  color: "#16151A",
                  fontSize: 13.5,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                onClick={() => {
                  s.toast("변경 사항을 저장했어요");
                  router.push("/studio");
                }}
              >
                변경 사항 저장
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
