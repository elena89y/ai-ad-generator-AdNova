import LegalPage from "@/components/LegalPage";
import { privacySections } from "@/lib/legal-content";

export default function PrivacyPage() {
  return (
    <LegalPage
      title="개인정보처리방침"
      description="AdNova Studio가 개인정보를 수집하고 처리하는 방법을 안내합니다."
      sections={privacySections}
    />
  );
}