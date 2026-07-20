import LegalPage from "@/components/LegalPage";
import { termsSections } from "@/lib/legal-content";

export default function TermsPage() {
  return (
    <LegalPage
      title="이용약관"
      description="AdNova Studio 서비스 이용에 적용되는 기본 조건입니다."
      sections={termsSections}
    />
  );
}