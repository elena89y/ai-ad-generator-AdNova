import type { Metadata } from "next";
import { Instrument_Serif, Space_Grotesk } from "next/font/google";
import localFont from "next/font/local";
import ChatWidget from "@/components/support/ChatWidget";
import "./globals.css";

const pretendard = localFont({
  src: [
    { path: "../fonts/pretendard-400.woff2", weight: "400" },
    { path: "../fonts/pretendard-500.woff2", weight: "500" },
    { path: "../fonts/pretendard-600.woff2", weight: "600" },
    { path: "../fonts/pretendard-700.woff2", weight: "700" },
    { path: "../fonts/pretendard-800.woff2", weight: "800" },
    { path: "../fonts/pretendard-900.woff2", weight: "900" },
  ],
  variable: "--font-pretendard",
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "AdNova — 제품 사진 한 장이 광고가 되기까지, 몇 초",
  description:
    "상품 사진을 업로드하면 AI가 광고 이미지와 카피를 자동으로 만들어줍니다. 소상공인을 위한 AI 광고 생성 플랫폼, AdNova.",
  icons: { icon: "/brand/favicon.png" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      data-scroll-behavior="smooth"
      className={`${pretendard.variable} ${spaceGrotesk.variable} ${instrumentSerif.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        {children}
        {/* 고객센터 챗봇(노바냥) — 모든 페이지 우측 하단 상시 */}
        <ChatWidget />
      </body>
    </html>
  );
}
