"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  AdItem,
  GenerateResult,
  PlatformCopy,
  STYLE_PRESET_MAP,
  apiFetch,
  classifyProduct,
  formatDateLabel,
  formatSizeBadge,
  getToken,
  normalizePlatformCopy,
  readApiError,
  readJsonSafely,
  splitCopyText,
  toAbsoluteUrl,
  toStyleLabel,
} from "@/lib/api";
import { containsEmoji } from "@/lib/input-validation";
import { useStudio } from "@/components/studio/StudioProvider";
import { AppBar, WorkspaceNav } from "@/components/studio/chrome";
import { AuthenticatedImage } from "@/components/studio/AuthenticatedImage";

const GEN_STEPS = [
  "사진을 분석하는 중…",
  "스타일을 입히는 중…",
  "광고 문구를 쓰는 중…",
  "마무리하는 중…",
];

const STYLES: { label: string; sw: string }[] = [
  { label: "웜 빈티지", sw: "linear-gradient(135deg,#F2A93B,#C42E5C)" },
  { label: "모노톤", sw: "linear-gradient(135deg,#e8e6ea,#9a95a5)" },
  { label: "팝 비비드", sw: "linear-gradient(135deg,#5BC0EB,#C42E5C)" },
  { label: "에디토리얼", sw: "linear-gradient(135deg,#17151C,#8A7C9A)" },
  { label: "리얼리즘", sw: "linear-gradient(135deg,#6B8F71,#D8C8A8)" },
  { label: "파스텔", sw: "linear-gradient(135deg,#F6D8E4,#D9F0E6)" },
];

const USES = [
  { v: "sns", label: "SNS" },
  { v: "card", label: "카드뉴스" },
  { v: "banner", label: "배너" },
  // [html-parity] 전단지 폐기 결정 반영 — 모놀리식 html은 이미 상세페이지로 교체됨
  { v: "detail", label: "상세페이지" },
];

/* [html-parity] 포맷 갤러리 라벨 — 모놀리식 html FORMAT_GALLERY_LABELS 이식.
   Next 이관에서 format_outputs 갤러리 자체가 누락되어 있었음 (index.html renderFormatGallery) */
const FORMAT_GALLERY_LABELS: Record<string, string> = {
  sns: "이미지",
  card_news: "카드뉴스",
  banner: "배너 규격",
  detail_page: "상세페이지",
};

/* [html-parity] 용도 버튼 값 → 백엔드 purpose — 모놀리식 html getSelectedPurpose 이식.
   Next 이관에서는 useValue가 페이로드에 실리지 않아 용도 버튼이 무동작이었음 */
function resolvePurpose(value: string): string {
  return value === "banner"
    ? "banner"
    : value === "card"
      ? "card_news"
      : value === "detail"
        ? "detail_page"
        : "sns";
}

const PLATFORMS = [
  { p: "instagram", si: "ig", label: "Instagram", short: "IG" },
  { p: "facebook", si: "fb", label: "Facebook", short: "f" },
  { p: "x", si: "x", label: "X", short: "X" },
  { p: "threads", si: "th", label: "Threads", short: "@" },
];

/* 상품명 → 광고 유형 자동 감지 (프로토타입 detectMode 포팅).
   SRV-ROUTE-001 phase2: 타이핑 중 근사 미리보기 전용 — 생성 후에는 백엔드 serving_type
   (SERVING_TYPE_LABELS)이 정본. 디저트·베이커리를 음료에서 분리(케이크가 "카페 음료"로
   뜨던 문제). 기존 `티\b`는 JS \b가 한글 경계를 못 잡아 사문(死文)이라 명시 차 어휘로 대체. */
function detectModeText(name: string): string {
  const n = (name || "").trim();
  const dessert =
    /(쿠키|스콘|케이크|케익|마카롱|크루아상|도넛|타르트|빵|베이글|디저트|와플|브라우니|푸딩|아이스크림|빙수|치아바타|바게트|바게뜨|깜빠뉴|캉파뉴|포카치아|프레첼|브레첼|브리오슈|치즈케익|카스테라|카스텔라|마들렌|휘낭시에|파이|소보로|페이스트리|페스츄리|롤케이크|파운드|머핀|컵케이크)/;
  const drink =
    /(라떼|밀크티|커피|아메리카노|콜드브루|에스프레소|스무디|에이드|주스|음료|홍차|녹차|레모네이드)/;
  /* 정육·해산물은 개별 품목이 아니라 카테고리 어휘로 넓게 잡는다(살치살→'살치', 꽃등심→'등심',
     소/돼지/닭고기→'고기'). 목록에 없는 음식은 아래 중립 폴백이 백엔드 analyze_menu(LLM)로
     넘기므로 정본은 그쪽이다 — 여기를 전수 하드코딩할 필요는 없다. */
  const food =
    /(밥|국|탕|찌개|전골|구이|볶음|조림|찜|튀김|무침|면|국수|파스타|라면|우동|김밥|덮밥|비빔|정식|백반|치킨|피자|버거|샌드위치|스테이크|고기|육회|불고기|수육|편육|한우|삼겹|오겹|갈비|목살|목심|등심|안심|채끝|살치|부채살|토시살|제비추리|갈매기살|차돌|치마살|항정|가브리살|곱창|막창|대창|족발|보쌈|회|초밥|새우|오징어|낙지|문어|주꾸미|조개|전복|굴|연어|참치|장어|고등어|해물|해산물|카레|떡볶이|순대|만두|전|죽|샐러드)/;
  /* 2026-07-28 리포트: "보석 모양 비누"·"히알루론산 세럼"이 음식으로 표시됨. 백엔드
     analyze_menu 는 셋 다 object 로 정확히 분류하므로(실측) 원인은 이 미리보기 정규식 —
     화장품·세면용품 어휘가 거의 없고, 미등록어는 폴백이 곧바로 "음식"이었다. 어휘를 넓히고,
     확신이 없으면 음식이라 단정하지 않는 중립 문구로 끝낸다. */
  const obj =
    /(마우스|키보드|컵|잔|텀블러|케이스|가방|시계|이어폰|스탠드|괄사|기기|용품|가전|조명|램프|의자|책상|화장품|스킨케어|세럼|앰플|에센스|토너|로션|크림|선크림|클렌징|마스크팩|립밤|향수|디퓨저|캔들|향초|비누|입욕제|바디워시|샴푸|트리트먼트|핸드크림|네일|브러시|파우치|텀블러|보틀|머그|접시|도마|수건|양말|의류|티셔츠|모자|반지|목걸이|귀걸이|팔찌|키링|인형|장난감|문구|노트|볼펜|사료)/;
  if (!n) return "상품명을 입력하면 광고 유형을 자동 판단해요";
  /* 음식 이름이 붙은 사물(컵케이크 캔들·마카롱 키링)은 먼저 사물로 확정한다 — 뒤의 음식
     어휘 검사에 걸리면 디저트로 오판한다. */
  const objHead = /(캔들|향초|디퓨저|비누|키링|인형|스티커|방향제|워머|모형)/;
  if (objHead.test(n)) return "사물·제품으로 인식 · 스튜디오 배경 모드";
  /* 그 다음 음식 계열 — 음식명 안에 사물 어휘가 섞이는 경우("크림 펜네 파스타"의 '펜')를
     사물로 오판하지 않게, 사물 일반 판정은 맨 뒤에 둔다. */
  if (dessert.test(n)) return "디저트·베이커리로 인식 · 배경 연출 모드";
  if (drink.test(n)) return "카페 음료로 인식 · 배경 연출 모드";
  if (food.test(n)) return "음식으로 인식 · 정체성 보존 향상 모드";
  if (obj.test(n)) return "사물·제품으로 인식 · 스튜디오 배경 모드";
  /* 미등록어는 음식이라 단정하지 않는다 — 생성 후 백엔드 serving_type 이 정본으로 덮어쓴다. */
  return "생성하면 광고 유형을 자동 판단해요";
}

/* SRV-ROUTE-001 phase2: 백엔드 serving_type → 정본 인식 라벨. 미지값·부재는 regex 폴백. */
const SERVING_TYPE_LABELS: Record<string, string> = {
  dish: "음식으로 인식 · 정체성 보존 향상 모드",
  drink: "카페 음료로 인식 · 배경 연출 모드",
  dessert: "디저트·베이커리로 인식 · 배경 연출 모드",
  bakery: "디저트·베이커리로 인식 · 배경 연출 모드",
  object: "사물·제품으로 인식 · 스튜디오 배경 모드",
};

export default function StudioPage() {
  const s = useStudio();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [loadStep, setLoadStep] = useState(GEN_STEPS[0]);
  const [activePlatform, setActivePlatform] = useState("instagram");
  // [html-parity] 타이포 토글 상태 — html #typographyToggle 이식 (Next 이관 시 누락)
  const [typographyOn, setTypographyOn] = useState(true);
  // 02·스타일 탭: 무드 프리셋 선택(preset) vs 자유서술(custom). 자유서술은 style_text로 전송.
  const [styleMode, setStyleMode] = useState<"preset" | "custom">("preset");
  const [styleText, setStyleText] = useState("");
  const [uploadInfo, setUploadInfo] = useState(
    "사진만 넣으면 배경·구도는 AI가 알아서 잡아줘요."
  );
  // 상품명 → 백엔드 LLM 분류(생성 전 미리보기). 정규식 즉시 힌트 위에 덮어써 어휘 갭을 메운다.
  const [livePreview, setLivePreview] = useState<{ name: string; serving: string | null }>({
    name: "",
    serving: null,
  });
  const stepTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const productNameHasEmoji = containsEmoji(s.prodName);
  const extraRequestHasEmoji = containsEmoji(s.promptText);
  const hasEmojiInput = productNameHasEmoji || extraRequestHasEmoji;

  useEffect(() => {
    if (s.ready && !s.token) router.replace("/login");
  }, [s.ready, s.token, router]);

  useEffect(() => {
    s.refreshDashboardSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 상품명 입력이 멈추면(600ms 디바운스) 백엔드 analyze_menu(LLM)로 유형 판정 — 정규식이 못
  // 잡는 정육·베이커리·지역음식 등을 범용으로 인식(생성과 동일 분류). 로그인 + 2자 이상만 호출,
  // lru_cache로 같은 이름은 무료. 정규식이 라벨에서 즉시 폴백이라 이 호출 전에도 힌트는 보인다.
  useEffect(() => {
    const name = s.prodName.trim();
    if (!s.token || name.length < 2) return;
    const timer = setTimeout(async () => {
      const r = await classifyProduct(name);
      if (r?.serving_type) setLivePreview({ name, serving: r.serving_type });
    }, 600);
    return () => clearTimeout(timer);
  }, [s.prodName, s.token]);

  const platformCopy: PlatformCopy | null = s.currentResult
    ? currentCopyFor(activePlatform, s.currentResult)
    : null;

  function currentCopyFor(platform: string, result: GenerateResult): PlatformCopy {
    const copy = splitCopyText(result.copy_text);
    const fallback: PlatformCopy = {
      head: copy.head,
      body: copy.body,
      tags: `#AI광고 #AdNova #${toStyleLabel(result.style)}`,
    };
    return normalizePlatformCopy(result.platform_copies?.[platform], fallback);
  }

  function selectProductImage() {
    if (!getToken()) {
      s.toast("로그인 후 이미지를 업로드해 주세요");
      router.push("/login");
      return;
    }
    fileRef.current?.click();
  }

  function selectImageFile(file: File | undefined) {
    // 백엔드 MAX_IMAGE_SIZE_MB(운영 10MB)와 동기 — 서버가 장변 2048로 정규화 저장하므로 폰 원본 OK
    const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
    if (!file) return;
    if (file.size > MAX_IMAGE_SIZE) {
      s.toast("이미지는 최대 10MB까지 업로드할 수 있습니다.");
      return;
    }
    const nextPreview = URL.createObjectURL(file);
    s.setDashboardState({
      selectedImageId: null,
      selectedImageUrl: null,
      selectedImagePreview: nextPreview,
      selectedImageFile: file,
      currentResult: null,
    });
    setUploadInfo(`선택한 이미지: ${file.name}`);
    s.toast("이미지를 선택했습니다");
  }

  function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    selectImageFile(e.target.files?.[0]);
    e.target.value = "";
  }

  function handleImageDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    selectImageFile(e.dataTransfer.files?.[0]);
  }

  function removeSelectedImage() {
    s.setDashboardState({
      selectedImageId: null,
      selectedImageUrl: null,
      selectedImagePreview: null,
      selectedImageFile: null,
      currentResult: null,
    });
    setUploadInfo("사진만 넣으면 배경·구도는 AI가 알아서 잡아줘요.");
    s.toast("선택한 이미지를 제거했습니다");
  }

  function startLoadingSteps() {
    let i = 0;
    setLoadStep(GEN_STEPS[0]);
    stepTimer.current = setInterval(() => {
      i++;
      if (i < GEN_STEPS.length) setLoadStep(GEN_STEPS[i]);
    }, 900);
  }
  function stopLoadingSteps() {
    if (stepTimer.current) clearInterval(stepTimer.current);
  }

  async function notifyHistorySaved(data: GenerateResult, message: string) {
    const ads = await s.refreshHistory(false);
    const isSaved = Boolean(data.history_id) && ads.some((ad) => ad.historyId === data.history_id);
    s.toast(
      isSaved
        ? message
        : "광고는 생성됐지만 내 광고 목록 반영을 확인하지 못했습니다. 잠시 후 다시 확인해 주세요."
    );
  }

  async function generate() {
    if (!s.billingReady) {
      s.toast("구독 정보를 확인한 뒤 광고를 생성할 수 있습니다");
      return;
    }
    // 보너스 크레딧은 백엔드(_consume_generation_credit)에서 1순위로 소비된다.
    // 보너스가 남아 있으면 프리미엄/무료 소진과 무관하게 생성 허용(프리미엄 소진 오차단 방지).
    if (s.bonusLeft <= 0) {
      if (s.isPremium && s.premiumLeft <= 0) {
        s.toast("이번 달 프리미엄 크레딧을 모두 사용했습니다");
        return;
      }
      if (!s.isPremium && s.freeLeft <= 0) {
        s.setUpgradeOpen(true);
        return;
      }
    }
    if (!getToken()) {
      s.toast("로그인 후 광고를 생성해 주세요");
      router.push("/login");
      return;
    }
    if (!s.selectedImageFile && !s.selectedImageId) {
      s.toast("먼저 제품 사진을 업로드해 주세요");
      return;
    }
    const productName = s.prodName.trim();
    if (!productName) {
      s.toast("상품명을 입력해 주세요");
      return;
    }
    if (hasEmojiInput) {
      s.toast("상품명과 추가 요청에서는 이모티콘을 사용할 수 없습니다");
      return;
    }

    setLoading(true);
    startLoadingSteps();
    const formData = new FormData();
    if (s.selectedImageId) {
      formData.append("image_id", String(s.selectedImageId));
    } else if (s.selectedImageFile) {
      formData.append("image", s.selectedImageFile);
    }
    formData.append("product_name", productName);
    formData.append("product_description", s.promptText.trim());
    formData.append("style", STYLE_PRESET_MAP[s.styleLabel] || "pop");
    formData.append("use_vision", "false");
    // 자유서술 무드(직접 입력 탭) — base 프리셋 위에 연출로 가산. 백엔드가 영문 번역 후 주입.
    if (styleMode === "custom" && styleText.trim()) {
      formData.append("style_text", styleText.trim());
    }
    const purpose = resolvePurpose(s.useValue);
    // [html-parity] html generate와 동일하게 purpose 전송 + sns 용도만 poster=true.
    // 이관 직후엔 poster="false" 하드코딩 + purpose 미전송으로 용도 선택이 무시됐음.
    formData.append("poster", String(purpose === "sns"));
    formData.append("purpose", purpose);

    try {
      const res = await apiFetch("/api/ads/generate", { method: "POST", body: formData });
      const data = (await readJsonSafely(res)) as GenerateResult | null;
      if (!res.ok || !data)
        throw new Error(readApiError(data, "광고 생성에 실패했습니다"));
      s.setDashboardState({ currentResult: { ...data, client_prod_name: productName } });
      s.refreshBilling(false);
      s.refreshDashboardSummary();
      await notifyHistorySaved(data, "광고가 생성되었습니다");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "광고 생성에 실패했습니다");
    } finally {
      stopLoadingSteps();
      setLoading(false);
    }
  }

  async function regenerate() {
    if (!s.billingReady) {
      s.toast("구독 정보를 확인한 뒤 다시 생성할 수 있습니다");
      return;
    }
    // 보너스 크레딧은 백엔드(_consume_generation_credit)에서 1순위로 소비된다.
    // 보너스가 남아 있으면 프리미엄/무료 소진과 무관하게 생성 허용(프리미엄 소진 오차단 방지).
    if (s.bonusLeft <= 0) {
      if (s.isPremium && s.premiumLeft <= 0) {
        s.toast("이번 달 프리미엄 크레딧을 모두 사용했습니다");
        return;
      }
      if (!s.isPremium && s.freeLeft <= 0) {
        s.setUpgradeOpen(true);
        return;
      }
    }
    if (!s.currentResult?.asset_id) {
      s.toast("먼저 광고를 생성해 주세요");
      return;
    }
    const productName = s.prodName.trim();
    if (!productName) {
      s.toast("상품명을 입력해 주세요");
      return;
    }
    setLoading(true);
    startLoadingSteps();
    try {
      const res = await apiFetch("/api/ads/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          asset_id: s.currentResult.asset_id,
          style: STYLE_PRESET_MAP[s.styleLabel] || "pop",
          product_name: productName,
          product_description: s.promptText.trim(),
          prev_seed: s.currentResult.seed,
          use_vision: false,
          // [html-parity] html regenerate와 동일 — 이관 시 poster:false 하드코딩·purpose 누락
          poster: resolvePurpose(s.useValue) === "sns",
          purpose: resolvePurpose(s.useValue),
        }),
      });
      const data = (await readJsonSafely(res)) as GenerateResult | null;
      if (!res.ok || !data)
        throw new Error(readApiError(data, "다시 생성에 실패했습니다"));
      s.setDashboardState({ currentResult: { ...data, client_prod_name: productName } });
      s.refreshBilling(false);
      s.refreshDashboardSummary();
      await notifyHistorySaved(data, "광고를 다시 생성했습니다");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "다시 생성에 실패했습니다");
    } finally {
      stopLoadingSteps();
      setLoading(false);
    }
  }

  function buildCurrentOutputItem(): AdItem | null {
    if (!s.currentResult) return null;
    const productName = s.prodName.trim() || "광고 상품";
    const copy = currentCopyFor(activePlatform, s.currentResult);
    return {
      historyId: s.currentResult.history_id,
      emoji: "✦",
      hl: copy.head || productName,
      copyHead: copy.head || productName,
      copyBody: copy.body || s.currentResult.copy_text || "",
      copyTags: copy.tags || "",
      platformCopies: s.currentResult.platform_copies || {},
      // 직접입력(자유서술)은 무드 선택이 없으니 base style 대신 '직접입력' 표시(갤러리/상세와 일치).
      style:
        styleMode === "custom" && styleText.trim()
          ? "직접입력"
          : toStyleLabel(s.currentResult.style),
      rawStyle: s.currentResult.style,
      img: toAbsoluteUrl(resultImageUrl(s.currentResult)),
      // [html-parity] 상세·공유로 넘어가도 타이포 토글이 되도록 페어 유지 (html 이식)
      imageWithoutTypography: toAbsoluteUrl(s.currentResult.image_without_typography_url),
      imageWithTypography: toAbsoluteUrl(s.currentResult.image_with_typography_url),
      inputImg: "",
      assetId: s.currentResult.asset_id,
      seed: s.currentResult.seed,
      adType: s.currentResult.poster ? "poster" : "image",
      date: formatDateLabel(new Date().toISOString()),
      productName,
      g: "linear-gradient(150deg,#2C2140,#8A3A5A 55%,#E0912F)",
      prod: "linear-gradient(160deg,#fff6e6,#f4c988)",
    };
  }

  function shareCurrentResult() {
    const item = buildCurrentOutputItem();
    if (!item) {
      s.toast("먼저 광고를 생성해 주세요");
      return;
    }
    s.openShare(item, "/studio", activePlatform);
    router.push(
      item.historyId ? `/share?historyId=${item.historyId}` : "/share"
    );
  }

  // [html-parity] html downloadImageFile 이식 — 기존 downloadResult 본문과 통합해
  // 메인 결과 + 포맷 갤러리 공용. 인증 헤더 + 프리미엄 게이트 유지.
  async function downloadImage(url: string | undefined, filename: string) {
    if (!s.isPremium) {
      router.push("/billing");
      return;
    }
    if (!url) {
      s.toast("다운로드할 광고 이미지가 없습니다");
      return;
    }
    try {
      const res = await fetch(url, {
        headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
      });
      if (!res.ok) throw new Error("이미지를 불러오지 못했습니다");
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      s.toast("고해상도 원본을 다운로드했어요");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "광고 이미지를 다운로드하지 못했습니다");
    }
  }

  async function downloadResult() {
    await downloadImage(toAbsoluteUrl(resultImageUrl(s.currentResult)), "adnova-ad.png");
  }

  const result = s.currentResult;
  // [html-parity] html applyGeneratedResult/getResultImageUrl 이식 (Next 이관 시 누락).
  // 타이포 페어(포함/무타이포)가 모두 있을 때만 토글 노출. 없으면 image_url 폴백.
  // 타이포 토글은 '포함/없음' 두 이미지가 실제로 다를 때만 노출(템플릿=구운 단일본 with==without → 숨김).
  const hasTypographyPair = Boolean(
    result?.image_with_typography_url &&
      result?.image_without_typography_url &&
      result.image_with_typography_url !== result.image_without_typography_url,
  );
  const resultImageUrl = (r: GenerateResult | null, on = typographyOn) => {
    if (!r) return undefined;
    return on
      ? r.image_with_typography_url || r.image_url
      : r.image_without_typography_url || r.image_url;
  };
  const beforeSrc =
    s.selectedImagePreview ??
    toAbsoluteUrl(s.selectedImageUrl) ??
    "";

  return (
    <section>
      <AppBar />
      <div className="dashboard-layout with-wsnav">
        <WorkspaceNav />
        {/* CONTROL RAIL */}
        <div className="control-rail">
          <div>
            <div className="rail-label">01 · 재료</div>
            <div
              style={{
                position: "relative",
                height: 150,
                borderRadius: 12,
                overflow: "hidden",
                border: beforeSrc
                  ? "1px solid var(--line)"
                  : "1px dashed rgba(255,255,255,.2)",
                background: beforeSrc
                  ? "var(--card)"
                  : "rgba(255,255,255,.025)",
                cursor: "pointer",
                transition: "border-color .2s ease, background .2s ease",
              }}
              onClick={selectProductImage}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleImageDrop}
            >
              {beforeSrc ? (
                <>
                  <AuthenticatedImage
                    src={beforeSrc}
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      display: "block",
                    }}
                    alt="제품 사진"
                  />

                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      selectProductImage();
                    }}
                    style={{
                      position: "absolute",
                      top: 8,
                      right: 8,
                      background: "rgba(0,0,0,.65)",
                      color: "#fff",
                      fontSize: 11,
                      fontWeight: 700,
                      padding: "5px 10px",
                      borderRadius: 8,
                      backdropFilter: "blur(6px)",
                      border: 0,
                      cursor: "pointer",
                    }}
                  >
                    사진 바꾸기
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeSelectedImage();
                    }}
                    style={{
                      position: "absolute",
                      right: 8,
                      bottom: 8,
                      background: "rgba(0,0,0,.65)",
                      color: "#fff",
                      fontSize: 11,
                      fontWeight: 700,
                      padding: "5px 10px",
                      borderRadius: 8,
                      backdropFilter: "blur(6px)",
                      border: 0,
                      cursor: "pointer",
                    }}
                  >
                    제거
                  </button>
                </>
              ) : (
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 7,
                    textAlign: "center",
                    padding: 16,
                  }}
                >
                  <div
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: 11,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      background: "rgba(255,255,255,.06)",
                      border: "1px solid rgba(255,255,255,.08)",
                      fontSize: 18,
                    }}
                  >
                    📷
                  </div>

                  <div
                    style={{
                      color: "var(--ink)",
                      fontSize: 13,
                      fontWeight: 700,
                    }}
                  >
                    제품 사진 업로드
                  </div>

                  <div
                    style={{
                      color: "var(--ink-mute)",
                      fontSize: 11,
                      lineHeight: 1.4,
                    }}
                  >
                    클릭하거나 파일을 끌어다 놓으세요
                  </div>
                </div>
              )}
            </div>
            <div
              style={{
                fontSize: 11,
                color: "var(--ink-mute)",
                marginTop: 8,
                lineHeight: 1.5,
              }}
            >
              {uploadInfo}
            </div>
            <label className="mini-label">
              상품명 <span className="hint">· 입력하면 분위기를 자동으로</span>
            </label>
            <input
              className="rail-input"
              placeholder="예: 카페 라떼, 흑당 밀크티"
              value={s.prodName}
              onChange={(e) => s.setDashboardState({ prodName: e.target.value })}
            />
            {productNameHasEmoji && (
              <div className="field-error" style={{ color: "#e5484d", fontSize: 12, marginTop: 4 }}>
                상품명에는 이모티콘을 사용할 수 없습니다.
              </div>
            )}
            <div className="auto-mode" style={{ margin: "9px 0 0" }}>
              <span className="lamp" />
              {/* SRV-ROUTE-001 phase2: 생성 후엔 백엔드 인식값이 정본, 이름을 바꿔 치는 중이면
                  (client_prod_name 불일치) regex 미리보기로 복귀 — stale 라벨 방지 */}
              <span>
                {(s.currentResult?.serving_type &&
                  s.currentResult?.client_prod_name === s.prodName.trim()
                  ? SERVING_TYPE_LABELS[s.currentResult.serving_type]
                  : undefined) ??
                  (livePreview.serving && livePreview.name === s.prodName.trim()
                    ? SERVING_TYPE_LABELS[livePreview.serving]
                    : undefined) ??
                  detectModeText(s.prodName)}
              </span>
            </div>
            <label className="mini-label">
              추가 요청 <span className="hint">· 선택</span>
            </label>
            <textarea
              className="rail-textarea"
              placeholder="예: 시원한 여름 느낌 강조, 20대 타깃"
              value={s.promptText}
              onChange={(e) => s.setDashboardState({ promptText: e.target.value })}
            />
            {extraRequestHasEmoji && (
              <div className="field-error" style={{ color: "#e5484d", fontSize: 12, marginTop: 4 }}>
                추가 요청에는 이모티콘을 사용할 수 없습니다.
              </div>
            )}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              {["할인 이벤트 강조", "신메뉴 출시", "인스타 감성"].map((tip) => (
                <span
                  key={tip}
                  className="chip-tip"
                  onClick={() =>
                    s.setDashboardState({
                      promptText: (s.promptText.trim() + " " + tip).trim(),
                    })
                  }
                >
                  + {tip.replace(" 강조", "").replace("강조", "")}
                </span>
              ))}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*,.heic,.heif"
              hidden
              onChange={handleImageUpload}
            />
          </div>
          <div style={{ height: 1, background: "var(--line)" }} />
          <div>
            <div className="rail-label">02 · 스타일</div>
            <div
              style={{
                display: "flex",
                background: "rgba(255,255,255,.05)",
                borderRadius: 9,
                padding: 3,
                marginBottom: 11,
              }}
            >
              {([
                ["preset", "🎨 무드"],
                ["custom", "✍️ 직접 입력"],
              ] as const).map(([mode, label]) => (
                <div
                  key={mode}
                  onClick={() => setStyleMode(mode)}
                  style={{
                    flex: 1,
                    textAlign: "center",
                    padding: 7,
                    borderRadius: 7,
                    fontSize: 11.5,
                    fontWeight: styleMode === mode ? 700 : 600,
                    background: styleMode === mode ? "rgba(242,169,59,.16)" : "transparent",
                    color: styleMode === mode ? "var(--gold)" : "var(--ink-mute)",
                    cursor: "pointer",
                  }}
                >
                  {label}
                </div>
              ))}
            </div>
            {styleMode === "preset" ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {STYLES.map(({ label, sw }) => (
                  <button
                    key={label}
                    className={`style-row${s.styleLabel === label ? " on" : ""}`}
                    onClick={() => s.setDashboardState({ styleLabel: label })}
                  >
                    <span className="sw" style={{ background: sw }} />
                    <span className="nm">{label}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div>
                <textarea
                  className="rail-textarea"
                  placeholder="어떤 느낌으로 만들어 드릴까요? 편하게 적어주세요"
                  value={styleText}
                  onChange={(e) => setStyleText(e.target.value)}
                />
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                  {["더 먹음직스럽게", "고급스러운 그릇에", "따뜻한 햇살 느낌", "깔끔한 여백"].map(
                    (c) => (
                      <span
                        key={c}
                        className="chip-tip"
                        onClick={() =>
                          setStyleText((t) => (t.trim() ? `${t.trim()}, ${c}` : c))
                        }
                      >
                        + {c}
                      </span>
                    )
                  )}
                  {/* '이미지만' = 글자 빼기 모드 칩 (스타일 칩과 성격이 달라 라벨을 명확히). */}
                  <span
                    className="chip-tip"
                    onClick={() =>
                      setStyleText((t) => (t.trim() ? `${t.trim()}, 이미지만` : "이미지만"))
                    }
                  >
                    + 이미지만 (글자 없이)
                  </span>
                </div>
                <p className="hint" style={{ marginTop: 8 }}>
                  같은 음식을 더 맛있고 고급스럽게 연출해 드려요. 양과 재료는 사실 그대로 유지합니다.
                  <br />
                  헤드라인 글자까지 이미지에 함께 만들어 드려요. 글자 없이 이미지만 원하시면 “이미지만”이라고
                  적어 주세요.
                </p>
              </div>
            )}
          </div>
          <div>
            <div className="rail-label">03 · 용도</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {USES.map(({ v, label }) => (
                <button
                  key={v}
                  className={`use${s.useValue === v ? " on" : ""}`}
                  onClick={() => s.setDashboardState({ useValue: v })}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <button
            className="btn-gen"
            style={{ marginTop: "auto" }}
            disabled={loading || hasEmojiInput}
            onClick={generate}
          >
            ✦ 광고 생성
          </button>
        </div>

        {/* CANVAS — 넓은 화면에서 결과·비교 카드가 통째로 퍼지지 않게 max-width 고정 + 중앙정렬 */}
        <div style={{ padding: 26, display: "flex", flexDirection: "column", gap: 16, width: "100%", maxWidth: 760, margin: "0 auto" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ fontSize: 13, color: "var(--ink-mute)" }}>
              결과{" "}
              <span style={{ color: "var(--ink)", fontWeight: 600 }}>
                · 원본 ⟷ AI 생성
              </span>
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-mute)" }}>
              {s.dashboardSummaryText}
            </div>
          </div>

          {loading ? (
            <div
              className="loading-panel"
              style={{
                flex: 1,
                minHeight: 420,
                border: "1px solid var(--line)",
                borderRadius: 16,
                background: "var(--card)",
              }}
            >
              <div className="ring" />
              <div className="st">{loadStep}</div>
              <div className="stp">광고를 만들고 있어요 (보통 1분 내외)</div>
            </div>
          ) : !result ? (
            <div
              className="result-empty"
              style={{
                flex: 1,
                minHeight: 420,
                border: "1px solid var(--line)",
                borderRadius: 16,
                background: "var(--card)",
              }}
            >
              <div className="big">🖼</div>
              <h3>아직 만든 광고가 없어요</h3>
              <p>
                왼쪽에서 재료를 넣고 <b>광고 생성</b>을 눌러보세요.
              </p>
            </div>
          ) : (
            <div>
              {/* [html-parity] 타이포 포함 토글 — html #resultTypeOption 이식 (Next 이관 시 누락) */}
              {hasTypographyPair && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    marginBottom: 12,
                    padding: "10px 13px",
                    border: "1px solid var(--line)",
                    borderRadius: 10,
                    background: "var(--card)",
                  }}
                >
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: "var(--ink-soft)",
                    }}
                  >
                    타이포 포함
                  </span>
                  <label
                    htmlFor="typographyToggle"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 7,
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    <input
                      id="typographyToggle"
                      type="checkbox"
                      checked={typographyOn}
                      onChange={(e) => setTypographyOn(e.target.checked)}
                    />
                    {typographyOn ? "포함" : "무타이포"}
                  </label>
                </div>
              )}
              <div
                className="compare-grid"
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr",
                  alignItems: "start",
                  gap: 16,
                }}
              >
                <div
                  style={{
                    position: "relative",
                    borderRadius: 14,
                    overflow: "hidden",
                    background: "#0d0d10",
                  }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={beforeSrc}
                    style={{
                      display: "block",
                      width: "100%",
                      height: "auto",
                      objectFit: "contain",
                    }}
                    alt="원본"
                  />
                  <span
                    style={{
                      position: "absolute",
                      left: 12,
                      top: 12,
                      background: "rgba(0,0,0,.55)",
                      color: "var(--ink-soft)",
                      fontSize: 10,
                      fontWeight: 800,
                      letterSpacing: ".05em",
                      padding: "4px 9px",
                      borderRadius: 6,
                    }}
                  >
                    BEFORE
                  </span>
                </div>
                <div
                  style={{
                    position: "relative",
                    borderRadius: 14,
                    overflow: "hidden",
                    background: "#0d0d10",
                  }}
                >
                  <AuthenticatedImage
                    src={toAbsoluteUrl(resultImageUrl(result))}
                    style={{
                      display: "block",
                      width: "100%",
                      height: "auto",
                      objectFit: "contain",
                    }}
                    alt="AI 광고"
                  />
                  <span
                    style={{
                      position: "absolute",
                      left: 12,
                      top: 12,
                      background: "var(--gold)",
                      color: "#16151A",
                      fontSize: 10,
                      fontWeight: 800,
                      letterSpacing: ".05em",
                      padding: "4px 9px",
                      borderRadius: 6,
                    }}
                  >
                    AFTER
                  </span>
                  {!s.isPremium && (
                    <div
                      aria-label="AdNova 무료 버전 워터마크"
                      style={{
                        position: "absolute",
                        right: 16,
                        bottom: 16,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        pointerEvents: "none",
                        userSelect: "none",
                      }}
                    >
                      <Image
                        src="/brand/brand-logo.png"
                        alt="AdNova"
                        width={120}
                        height={38}
                        style={{
                          width: 104,
                          height: "auto",
                          opacity: 0.82,
                          filter: "drop-shadow(0 2px 4px rgba(0, 0, 0, 0.35))",
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* [html-parity] 포맷 갤러리 — html renderFormatGallery 이식 (Next 이관 시 누락).
                  용도별 산출물이 Next에서 안 보이던 원인. 인증 이미지라 AuthenticatedImage 사용 */}
              {(result.format_outputs?.length ?? 0) > 0 && (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(2,minmax(0,1fr))",
                    gap: 12,
                    marginTop: 16,
                  }}
                >
                  {result.format_outputs!.map((value, index) => {
                    const url = toAbsoluteUrl(value);
                    const label =
                      FORMAT_GALLERY_LABELS[result.purpose ?? ""] || "결과";
                    const alt =
                      result.format_outputs!.length > 1
                        ? `${label} ${index + 1}`
                        : label;
                    return (
                      <div
                        key={`${value}-${index}`}
                        style={{
                          position: "relative",
                          overflow: "hidden",
                          border: "1px solid var(--line)",
                          borderRadius: 12,
                          background: "#0d0d10",
                          minHeight: 180,
                        }}
                      >
                        <AuthenticatedImage
                          src={url}
                          alt={alt}
                          style={{
                            display: "block",
                            width: "100%",
                            height: "100%",
                            minHeight: 180,
                            objectFit: "contain",
                          }}
                        />
                        {formatSizeBadge(value) && (
                          <span
                            style={{
                              position: "absolute",
                              top: 8,
                              left: 8,
                              padding: "3px 8px",
                              borderRadius: 6,
                              background: "rgba(0,0,0,0.62)",
                              color: "#fff",
                              fontSize: 12,
                              fontWeight: 600,
                              letterSpacing: "0.02em",
                              pointerEvents: "none",
                              zIndex: 2,
                            }}
                          >
                            {formatSizeBadge(value)}
                          </span>
                        )}
                        <button
                          type="button"
                          className="oa download"
                          style={{
                            position: "absolute",
                            right: 10,
                            bottom: 10,
                            background: "rgba(22,21,26,.88)",
                          }}
                          onClick={() =>
                            downloadImage(
                              url,
                              `adnova-${result.purpose || "format"}-${index + 1}.jpg`,
                            )
                          }
                        >
                          다운로드
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <div
                className="copy-block"
                style={{
                  background: "var(--card)",
                  border: "1px solid var(--line)",
                  borderRadius: 14,
                  padding: "16px 18px",
                  marginTop: 16,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                    marginBottom: 12,
                    flexWrap: "wrap",
                  }}
                >
                  <span style={{ fontSize: 12, fontWeight: 800, color: "var(--gold-deep)" }}>
                    ✦ 매체별 카피
                  </span>
                  <div className="plat-tabs" style={{ margin: "0 0 0 auto" }}>
                    {PLATFORMS.map(({ p, si, label, short }) => (
                      <button
                        key={p}
                        className={`ptab${activePlatform === p ? " on" : ""}`}
                        onClick={() => setActivePlatform(p)}
                      >
                        <span className={`si ${si}`}>{short}</span>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <h4>{platformCopy?.head}</h4>
                <p style={{ whiteSpace: "pre-line" }}>{platformCopy?.body}</p>
                <div className="tags">{platformCopy?.tags}</div>
              </div>

              <div className="out-actions">
                <button className="oa" onClick={downloadResult}>
                  ⬇️ 다운로드 {s.isPremium ? "" : "🔒"}
                </button>
                <button className="oa" onClick={shareCurrentResult}>
                  ↗️ 공유
                </button>
                <button className="oa" disabled={loading} onClick={regenerate}>
                  🔄 다시 생성
                </button>
              </div>
              {!s.isPremium && (
                <div className="wm-row">
                  <span className="wm-l">🔖 무료는 워터마크 미리보기만 제공돼요</span>
                  <button className="wm-up" onClick={() => router.push("/billing")}>
                    원본 다운로드 (프리미엄) →
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
