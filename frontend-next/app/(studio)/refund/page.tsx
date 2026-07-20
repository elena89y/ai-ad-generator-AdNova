import LegalPage from "@/components/LegalPage";
import { refundSections } from "@/lib/legal-content";

export default function RefundPage() {
  return (
    <LegalPage
      title="환불 및 청약철회 정책"
      description="유료 플랜과 크레딧의 취소, 청약철회 및 환불 기준입니다."
      sections={refundSections}
    />
  );
}