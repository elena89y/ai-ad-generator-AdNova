import type { Metadata } from "next";
import StudioProvider from "@/components/studio/StudioProvider";
import { UpgradeModal } from "@/components/studio/chrome";
import "./studio.css";

export const metadata: Metadata = {
  title: "AdNova Studio — 소상공인 AI 광고 생성",
};

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="studio-root">
      <StudioProvider>
        {children}
        <UpgradeModal />
      </StudioProvider>
    </div>
  );
}
