/* 고객센터 챗봇 마스코트 "노바냥" — 코드 드로잉 SVG (외부 이미지 없음: 라이선스·용량 0) */

export default function CatIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* 귀 */}
      <path d="M14 26 L10 8 L26 16 Z" fill="#f8fafc" />
      <path d="M50 26 L54 8 L38 16 Z" fill="#f8fafc" />
      <path d="M15.5 22.5 L13 11.5 L23 16.5 Z" fill="#a78bfa" />
      <path d="M48.5 22.5 L51 11.5 L41 16.5 Z" fill="#a78bfa" />
      {/* 얼굴 */}
      <ellipse cx="32" cy="38" rx="22" ry="19" fill="#f8fafc" />
      {/* 눈 */}
      <ellipse cx="24" cy="35" rx="3" ry="4" fill="#1e1b4b" />
      <ellipse cx="40" cy="35" rx="3" ry="4" fill="#1e1b4b" />
      <circle cx="25" cy="33.6" r="1" fill="#fff" />
      <circle cx="41" cy="33.6" r="1" fill="#fff" />
      {/* 볼터치 */}
      <ellipse cx="18" cy="42" rx="3.4" ry="2" fill="#fbcfe8" opacity="0.85" />
      <ellipse cx="46" cy="42" rx="3.4" ry="2" fill="#fbcfe8" opacity="0.85" />
      {/* 코·입 */}
      <path d="M30.4 41 L33.6 41 L32 43.4 Z" fill="#8b5cf6" />
      <path
        d="M32 43.4 Q32 46 28.6 46.4 M32 43.4 Q32 46 35.4 46.4"
        stroke="#1e1b4b"
        strokeWidth="1.5"
        strokeLinecap="round"
        fill="none"
      />
      {/* 수염 */}
      <g stroke="#cbd5e1" strokeWidth="1.4" strokeLinecap="round">
        <path d="M6 38 L15 39.5" />
        <path d="M7 45 L15.5 44" />
        <path d="M58 38 L49 39.5" />
        <path d="M57 45 L48.5 44" />
      </g>
    </svg>
  );
}
