/* v6 T4 — 템플릿 카탈로그 v1 (46종, 정적 표시 데이터).
   원천: ~/Desktop/AdNova/템플릿/catalog.json — 생성 프롬프트는 서버측 보관, 클라이언트에 싣지 않는다.
   ledger_id 가 있으면 CTA 가 /studio?template={ledger_id} (팩 전체 적용), 없으면 ?style= 프리셋만. */

export interface CatalogTemplate {
  no: number;
  id: string;
  name: string;
  desc: string;
  family: string;
  finish: string;
  tags: string[];
  img: string;
  style_label: string;
  use: string;
  ledger_id: string | null;
}

export const CATALOG: CatalogTemplate[] = [
  {
    "no": 1,
    "id": "menu_poster",
    "name": "오늘의 메뉴 포스터",
    "desc": "메뉴명 타이포와 단색 배경으로 완성하는 정석 음식 포스터",
    "family": "poster_typo",
    "finish": "graphic",
    "tags": [
      "#포스터",
      "#음식",
      "#인스타피드",
      "#매장포스터"
    ],
    "img": "/tpl/01_menu_poster.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 2,
    "id": "drink_twopanel",
    "name": "시그니처 음료 2단 컷",
    "desc": "질감 매크로와 제품컷을 위아래로 잇는 시그니처 2단 구성",
    "family": "multi_panel",
    "finish": "photographic",
    "tags": [
      "#포스터",
      "#카페음료",
      "#여름",
      "#인스타피드"
    ],
    "img": "/tpl/02_drink_twopanel.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 3,
    "id": "brand_studio",
    "name": "브랜드 컬러 스튜디오 컷",
    "desc": "브랜드 컬러 스튜디오에서 제품만 주인공으로",
    "family": "studio",
    "finish": "photographic",
    "tags": [
      "#스튜디오컷",
      "#미니멀",
      "#스마트스토어",
      "#생활용품"
    ],
    "img": "/tpl/03_brand_studio.jpg",
    "style_label": "에디토리얼",
    "use": "sns",
    "ledger_id": "object_studio_sku"
  },
  {
    "no": 4,
    "id": "cream_engrave",
    "name": "크림 각인 타이포",
    "desc": "크림 위에 새기는 각인 한 줄",
    "family": "material_typo",
    "finish": "photographic",
    "tags": [
      "#타이포그래피",
      "#뷰티",
      "#감성",
      "#디저트"
    ],
    "img": "/tpl/04_cream_engrave.jpg",
    "style_label": "파스텔",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 5,
    "id": "steam_closeup",
    "name": "국물 김서림 클로즈업",
    "desc": "김이 오르는 국물의 온도를 그대로",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#국물요리",
      "#음식",
      "#인스타피드"
    ],
    "img": "/tpl/05_steam_closeup.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": "realism_food_hero"
  },
  {
    "no": 6,
    "id": "charcoal_grill",
    "name": "숯불 직화 무드",
    "desc": "숯불과 불꽃이 만드는 직화의 무드",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#구이",
      "#음식"
    ],
    "img": "/tpl/06_charcoal_grill.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 7,
    "id": "bunsik_pop",
    "name": "분식 세트 팝 포스터",
    "desc": "비비드 컬러로 튀는 분식 세트 포스터",
    "family": "poster_typo",
    "finish": "graphic",
    "tags": [
      "#포스터",
      "#분식",
      "#키치",
      "#인스타피드"
    ],
    "img": "/tpl/07_bunsik_pop.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": "pop_vivid_promo"
  },
  {
    "no": 8,
    "id": "ingredient_callout",
    "name": "재료 콜아웃 오버레이",
    "desc": "재료를 선과 박스로 짚어주는 분석형 컷",
    "family": "graphic_layout",
    "finish": "photographic",
    "tags": [
      "#레이아웃그래픽",
      "#음식",
      "#인스타피드"
    ],
    "img": "/tpl/08_ingredient_callout.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 9,
    "id": "delivery_thumb",
    "name": "배달앱 썸네일",
    "desc": "배달앱 등록에 바로 쓰는 클린 썸네일",
    "family": "studio",
    "finish": "photographic",
    "tags": [
      "#스튜디오컷",
      "#배달앱메뉴",
      "#음식"
    ],
    "img": "/tpl/09_delivery_thumb.jpg",
    "style_label": "모노톤",
    "use": "detail",
    "ledger_id": null
  },
  {
    "no": 10,
    "id": "menu_trio",
    "name": "메뉴판 3종 세트",
    "desc": "같은 톤으로 촬영한 듯한 메뉴 3종 세트",
    "family": "multi_panel",
    "finish": "photographic",
    "tags": [
      "#멀티팩",
      "#음식",
      "#매장포스터"
    ],
    "img": "/tpl/10_menu_trio.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 11,
    "id": "cafe_goldenhour",
    "name": "카페 창가 골든아워",
    "desc": "늦은 오후 창가의 골든아워 감성",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#카페음료",
      "#감성"
    ],
    "img": "/tpl/11_cafe_goldenhour.jpg",
    "style_label": "웜 빈티지",
    "use": "sns",
    "ledger_id": "warm_vintage_cafe"
  },
  {
    "no": 12,
    "id": "latteart_topview",
    "name": "라떼아트 탑뷰",
    "desc": "라떼아트가 주인공인 수직 탑뷰",
    "family": "studio",
    "finish": "photographic",
    "tags": [
      "#스튜디오컷",
      "#카페음료",
      "#탑뷰"
    ],
    "img": "/tpl/12_latteart_topview.jpg",
    "style_label": "모노톤",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 13,
    "id": "season_banner",
    "name": "시즌 신메뉴 배너",
    "desc": "시즌 신메뉴를 알리는 가로 배너",
    "family": "graphic_layout",
    "finish": "graphic",
    "tags": [
      "#배너",
      "#카페음료",
      "#여름"
    ],
    "img": "/tpl/13_season_banner.jpg",
    "style_label": "파스텔",
    "use": "banner",
    "ledger_id": null
  },
  {
    "no": 14,
    "id": "ice_macro",
    "name": "아이스 텍스처 매크로",
    "desc": "얼음과 과육의 청량한 초근접",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#카페음료",
      "#여름",
      "#질감"
    ],
    "img": "/tpl/14_ice_macro.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 15,
    "id": "dessert_crosssection",
    "name": "디저트 단면 히어로",
    "desc": "층이 살아있는 디저트 단면 히어로",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#디저트",
      "#질감"
    ],
    "img": "/tpl/15_dessert_crosssection.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 16,
    "id": "pastel_studio",
    "name": "파스텔 소프트 스튜디오",
    "desc": "파스텔 톤의 부드러운 뷰티 스튜디오",
    "family": "studio",
    "finish": "photographic",
    "tags": [
      "#스튜디오컷",
      "#뷰티",
      "#파스텔"
    ],
    "img": "/tpl/16_pastel_studio.jpg",
    "style_label": "파스텔",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 17,
    "id": "ripple_reflection",
    "name": "물결 리플렉션 컷",
    "desc": "잔잔한 수면 위 반사와 커스틱",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#뷰티",
      "#감성"
    ],
    "img": "/tpl/17_ripple_reflection.jpg",
    "style_label": "에디토리얼",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 18,
    "id": "mini_showcase",
    "name": "미니어처 진열장",
    "desc": "미니어처 진열장 속 앙증맞은 연출",
    "family": "playful",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#뷰티",
      "#미니어처"
    ],
    "img": "/tpl/18_mini_showcase.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 19,
    "id": "cozy_fabric",
    "name": "코지 패브릭 정물",
    "desc": "린넨과 아침빛의 포근한 정물",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#뷰티",
      "#내추럴"
    ],
    "img": "/tpl/19_cozy_fabric.jpg",
    "style_label": "웜 빈티지",
    "use": "sns",
    "ledger_id": "editorial_lookbook"
  },
  {
    "no": 20,
    "id": "citrus_fresh",
    "name": "시트러스 프레시 컷",
    "desc": "시트러스 원물과 함께하는 프레시 컷",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#뷰티",
      "#내추럴"
    ],
    "img": "/tpl/20_citrus_fresh.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 21,
    "id": "desk_setup",
    "name": "데스크 셋업 컷",
    "desc": "정돈된 데스크 위 테크 감성",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#전자제품",
      "#라이프스타일"
    ],
    "img": "/tpl/21_desk_setup.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 22,
    "id": "unwrap_moment",
    "name": "포장을 여는 순간",
    "desc": "크라프트 포장을 여는 설렘의 순간",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#감성",
      "#내추럴",
      "#인스타피드"
    ],
    "img": "/tpl/22_unwrap_moment.jpg",
    "style_label": "웜 빈티지",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 23,
    "id": "color_split",
    "name": "컬러 블록 그래픽",
    "desc": "컬러 블록이 만드는 그래픽 구도",
    "family": "graphic_layout",
    "finish": "graphic",
    "tags": [
      "#레이아웃그래픽",
      "#미니멀",
      "#생활용품"
    ],
    "img": "/tpl/23_color_split.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 24,
    "id": "giant_mini",
    "name": "자이언트 제품 미니 씬",
    "desc": "거대 제품과 미니 소품의 스케일 반전",
    "family": "playful",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#키치",
      "#생활용품"
    ],
    "img": "/tpl/24_giant_mini.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 25,
    "id": "white_standard",
    "name": "흰 배경 정석 컷",
    "desc": "커머스 규격 순백 배경 정석 컷",
    "family": "studio",
    "finish": "photographic",
    "tags": [
      "#흰배경",
      "#스마트스토어",
      "#생활용품"
    ],
    "img": "/tpl/25_white_standard.jpg",
    "style_label": "모노톤",
    "use": "detail",
    "ledger_id": null
  },
  {
    "no": 26,
    "id": "gradient_studio",
    "name": "그라데이션 스튜디오 팩",
    "desc": "그라데이션 배경의 시리즈 스튜디오",
    "family": "studio",
    "finish": "photographic",
    "tags": [
      "#스튜디오컷",
      "#미니멀",
      "#뷰티"
    ],
    "img": "/tpl/26_gradient_studio.jpg",
    "style_label": "에디토리얼",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 27,
    "id": "summer_vacance",
    "name": "여름 바캉스 연출",
    "desc": "수영장 옆 한여름의 바캉스 무드",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#여름",
      "#뷰티"
    ],
    "img": "/tpl/27_summer_vacance.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 28,
    "id": "seollal_bojagi",
    "name": "설날 선물세트 보자기",
    "desc": "보자기 매듭의 단정한 명절 선물",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#설날",
      "#감성"
    ],
    "img": "/tpl/28_seollal_bojagi.jpg",
    "style_label": "웜 빈티지",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 29,
    "id": "christmas_ornament",
    "name": "크리스마스 오너먼트",
    "desc": "오너먼트와 전구 보케의 홀리데이",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#크리스마스",
      "#감성"
    ],
    "img": "/tpl/29_christmas_ornament.jpg",
    "style_label": "웜 빈티지",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 30,
    "id": "butter_engrave",
    "name": "버터 각인 타이포",
    "desc": "버터 질감 위 각인 타이포",
    "family": "material_typo",
    "finish": "photographic",
    "tags": [
      "#타이포그래피",
      "#질감",
      "#감성",
      "#디저트"
    ],
    "img": "/tpl/30_butter_engrave.jpg",
    "style_label": "파스텔",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 31,
    "id": "doodle_mood",
    "name": "손글씨 낙서 무드",
    "desc": "폴라로이드와 손그림 낙서의 발랄함",
    "family": "playful",
    "finish": "graphic",
    "tags": [
      "#연출컷",
      "#키치",
      "#인스타피드"
    ],
    "img": "/tpl/31_doodle_mood.jpg",
    "style_label": "파스텔",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 32,
    "id": "story_pack",
    "name": "인스타 스토리 세로 팩",
    "desc": "스토리 규격에 맞춘 세로 리듬",
    "family": "multi_panel",
    "finish": "photographic",
    "tags": [
      "#멀티팩",
      "#인스타피드",
      "#카페음료"
    ],
    "img": "/tpl/32_story_pack.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 33,
    "id": "cheese_pull",
    "name": "치즈 풀링 클로즈업",
    "desc": "길게 늘어나는 치즈의 순간 포착",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#음식",
      "#질감"
    ],
    "img": "/tpl/33_cheese_pull.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 34,
    "id": "hansang_topview",
    "name": "김 오르는 한 상 탑뷰",
    "desc": "김 오르는 한식 한상의 탑뷰",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#음식",
      "#탑뷰",
      "#국물요리"
    ],
    "img": "/tpl/34_hansang_topview.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 35,
    "id": "midnight_spotlight",
    "name": "야식 스팟라이트",
    "desc": "스팟라이트 하나로 완성하는 야식 무드",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#음식",
      "#감성"
    ],
    "img": "/tpl/35_midnight_spotlight.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 36,
    "id": "newmenu_notice",
    "name": "신메뉴 공지 포스터",
    "desc": "NEW 뱃지와 함께 알리는 신메뉴 공지",
    "family": "poster_typo",
    "finish": "graphic",
    "tags": [
      "#포스터",
      "#음식",
      "#매장포스터"
    ],
    "img": "/tpl/36_newmenu_notice.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 37,
    "id": "half_compare",
    "name": "세트/반반 비교 2분할",
    "desc": "반반 메뉴를 좌우로 비교하는 2분할",
    "family": "multi_panel",
    "finish": "photographic",
    "tags": [
      "#멀티팩",
      "#음식"
    ],
    "img": "/tpl/37_half_compare.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 38,
    "id": "honest_ingredient",
    "name": "원재료 정직 컷",
    "desc": "생재료와 완성 요리를 나란히",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#음식",
      "#내추럴"
    ],
    "img": "/tpl/38_honest_ingredient.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 39,
    "id": "spicy_gauge",
    "name": "매운맛 단계 그래픽",
    "desc": "고추 게이지로 보여주는 매운맛 단계",
    "family": "graphic_layout",
    "finish": "graphic",
    "tags": [
      "#레이아웃그래픽",
      "#음식",
      "#키치"
    ],
    "img": "/tpl/39_spicy_gauge.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 40,
    "id": "takeout_info",
    "name": "포장·배달 안내 컷",
    "desc": "포장·배달 안내를 담은 정보 컷",
    "family": "graphic_layout",
    "finish": "graphic",
    "tags": [
      "#레이아웃그래픽",
      "#배달앱메뉴",
      "#매장포스터"
    ],
    "img": "/tpl/40_takeout_info.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 41,
    "id": "season_limited",
    "name": "계절 한정 무드",
    "desc": "살얼음 육수의 계절 한정 청량감",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#음식",
      "#여름"
    ],
    "img": "/tpl/41_season_limited.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 42,
    "id": "dessert_showcase",
    "name": "디저트 쇼케이스 진열",
    "desc": "쇼케이스 조명 아래 디저트 진열",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#디저트",
      "#카페음료"
    ],
    "img": "/tpl/42_dessert_showcase.jpg",
    "style_label": "웜 빈티지",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 43,
    "id": "review_event",
    "name": "리뷰 이벤트 안내",
    "desc": "리뷰 이벤트를 알리는 친근한 안내",
    "family": "poster_typo",
    "finish": "graphic",
    "tags": [
      "#포스터",
      "#인스타피드",
      "#매장포스터"
    ],
    "img": "/tpl/43_review_event.jpg",
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 44,
    "id": "morning_windowlight",
    "name": "아침 정식 창가 무드",
    "desc": "아침 햇살 창가의 백반 정식",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#연출컷",
      "#음식",
      "#내추럴"
    ],
    "img": "/tpl/44_morning_windowlight.jpg",
    "style_label": "웜 빈티지",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 45,
    "id": "diagonal_band",
    "name": "사선 밴드 메뉴 포스터",
    "desc": "사선 띠와 세리프 타이포의 미니멀 포스터",
    "family": "graphic_layout",
    "finish": "graphic",
    "tags": [
      "#포스터",
      "#레이아웃그래픽",
      "#미니멀",
      "#음식"
    ],
    "img": "/tpl/45_diagonal_band.jpg",
    "style_label": "에디토리얼",
    "use": "sns",
    "ledger_id": "pop_split_summer"
  },
  {
    "no": 46,
    "id": "sketch_board",
    "name": "스케치 보드 2분할",
    "desc": "실사와 도면 스케치의 상하 2분할",
    "family": "multi_panel",
    "finish": "graphic",
    "tags": [
      "#멀티팩",
      "#레이아웃그래픽",
      "#음식"
    ],
    "img": "/tpl/46_sketch_board.jpg",
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null
  },
  {
    "no": 47,
    "id": "cake_crosssection_macro",
    "name": "케익 단면 클로즈업",
    "desc": "단면의 층이 프레임을 가득 채우는 초근접 케이크 화보",
    "family": "scene",
    "finish": "photographic",
    "tags": [
      "#디저트",
      "#연출컷",
      "#질감",
      "#인스타피드"
    ],
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null,
    "img": "/tpl/47_cake_crosssection_macro.jpg"
  },
  {
    "no": 48,
    "id": "partial_closeup_callout",
    "name": "부분 클로즈업 오버레이",
    "desc": "재료를 선과 박스로 짚어주는 부분 클로즈업 오버레이",
    "family": "graphic_layout",
    "finish": "photographic",
    "tags": [
      "#디저트",
      "#레이아웃그래픽",
      "#음식"
    ],
    "style_label": "리얼리즘",
    "use": "sns",
    "ledger_id": null,
    "img": "/tpl/48_partial_closeup_callout.jpg"
  },
  {
    "no": 49,
    "id": "circular_typo_poster",
    "name": "원형 타이포 포스터",
    "desc": "바닥에 새긴 원형 타이포가 디저트를 감싸는 포스터",
    "family": "poster_typo",
    "finish": "graphic",
    "tags": [
      "#타이포그래피",
      "#포스터",
      "#디저트",
      "#음식"
    ],
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null,
    "img": "/tpl/49_circular_typo_poster.jpg"
  },
  {
    "no": 50,
    "id": "curve_banner_poster",
    "name": "곡선 배너 포스터",
    "desc": "곡선 리본 속 손글씨 메뉴명이 살아있는 포스터",
    "family": "poster_typo",
    "finish": "graphic",
    "tags": [
      "#타이포그래피",
      "#포스터",
      "#음식",
      "#디저트"
    ],
    "style_label": "팝 비비드",
    "use": "sns",
    "ledger_id": null,
    "img": "/tpl/50_curve_banner_poster.jpg"
  }
];
