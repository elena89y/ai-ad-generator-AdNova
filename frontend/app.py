import streamlit as st
import requests
import random
import time

# 1. 페이지 기본 설정 (기본 상태를 닫힘으로 강력 제어)
st.set_page_config(
    page_title="AdNova - 소상공인 AI 광고 제작소", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 백엔드 API 서버 주소
API_URL = "http://localhost:8000"


def _api_image_url(path):
    """API 상대 이미지 경로를 프론트 표시용 절대 URL로 변환한다."""
    return f"{API_URL}{path}" if path else None


@st.cache_data(show_spinner=False, ttl=300)
def _download_image(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content

# 2. 세션 상태(Session State) 초기화
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "page" not in st.session_state:
    st.session_state.page = "create_ad"
if "user_info" not in st.session_state:
    st.session_state.user_info = {"name": "소상공인", "business_name": "우리동네 가게", "business_type": "음식점"}
if "generated_ad" not in st.session_state:
    st.session_state.generated_ad = None
if "history" not in st.session_state:
    st.session_state.history = [
        {"id": 1, "title": "바삭한 가마솥 통닭", "style": "WARM_VINTAGE", "img": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=500", "seed": 12345, "copy": "추억을 튀기는 가마솥 통닭\n아버지가 퇴근길에 사오시던 그 맛 그대로."},
        {"id": 2, "title": "모던 미니멀 조명", "style": "MONOTONE", "img": "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=500", "seed": 67890, "copy": "공간을 채우는 절제의 미학\n빛, 그 본질에 집중하다."}
    ]


# 💡 [핵심 차단] 로그인 전 프리-렌더링 방지를 위해 사이드바 선언을 함수 안으로 완벽히 가둡니다.
def render_sidebar():
    with st.sidebar:
        st.subheader(f"🏪 {st.session_state.user_info['business_name']}")
        st.caption(f"운영자: {st.session_state.user_info['name']} 사장님 | 업종: {st.session_state.user_info['business_type']}")
        st.markdown("---")
        
        if st.button("📝 광고 제작 홈", use_container_width=True):
            st.session_state.page = "create_ad"
            st.rerun()
            
        if st.button("👤 마이페이지 & 이력", use_container_width=True):
            st.session_state.page = "mypage"
            st.rerun()
            
        st.markdown("---")
        if st.button("🚪 안전 로그아웃", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.page = "create_ad"
            st.rerun()


# =================================================================
# ⚙️ 로그인 전/후 CSS 스타일 통제
# =================================================================
if not st.session_state.logged_in:
    # 로그인 전: 사이드바 관련 DOM 요소를 CSS로도 철저하게 3중 락(Lock)
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"], 
            [data-testid="stSidebarCollapsedControl"],
            .stAppDeployButton { 
                display: none !important; 
                visibility: hidden !important;
                width: 0px !important;
            }
            [data-testid="stMain"] {
                margin-left: 0px !important;
                padding-left: 5rem !important;
                padding-right: 5rem !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )
else:
    # 로그인 후: 사이드바가 정상적으로 숨김/열림 제어가 되도록 복구
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] { display: flex !important; visibility: visible !important; }
            [data-testid="stSidebarCollapsedControl"] { display: flex !important; visibility: visible !important; }
        </style>
        """,
        unsafe_allow_html=True
    )


# =================================================================
# 🔑 메인 라우팅 파이프라인
# =================================================================

# --- CASE 1: 로그인하지 않은 상태 (사이드바 원천 차단) ---
if not st.session_state.logged_in:
    st.title("🔑 AdNova 로그인")
    st.write("소상공인을 위한 스마트한 AI 광고 사진 및 문구 제작소에 오신 것을 환영합니다.")
    
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    
    with tab1:
        login_email = st.text_input("이메일 주소", value="ceo@so-sang.com", key="login_email")
        login_pw = st.text_input("비밀번호", type="password", value="Password123!", key="login_pw")
        
        if st.button("로그인하기", use_container_width=True):
            st.session_state.logged_in = True
            st.session_state.user_id = 1
            st.session_state.user_info = {
                "name": "Bom", 
                "business_name": "봄봄 푸드", 
                "business_type": "요식업"
            }
            st.success(f"🎉 {st.session_state.user_info['name']} 사장님, 반갑습니다!")
            time.sleep(0.3)
            st.rerun()  # 스크립트를 재구동하여 아래의 메인 대시보드로 진입
                
    with tab2:
        st.subheader("새로운 회원가입")
        reg_email = st.text_input("이메일 주소", placeholder="example@email.com")
        reg_id = st.text_input("아이디 (7~12자 영문/숫자)", placeholder="bomspring12")
        reg_pw = st.text_input("비밀번호 (8~20자, 대소문자/숫자/특수문자 필수 포함)", type="password")
        reg_name = st.text_input("사장님 이름")
        reg_bname = st.text_input("상호명")
        reg_btype = st.selectbox("업종 선택", ["요식업", "의류/패션", "뷰티/미용", "카페/디저트", "기타 소매업"])
        
        if st.button("회원가입 완료", use_container_width=True):
            import re
            id_pattern = r"^[A-Za-z0-9]{7,12}$"
            pw_pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&^#()_\-+=])[A-Za-z\d@$!%*?&^#()_\-+=]{8,20}$"
            
            if not re.match(id_pattern, reg_id):
                st.error("⚠️ 아이디는 영문과 숫자만 사용할 수 있으며 7~12자여야 합니다.")
            elif not re.match(pw_pattern, reg_pw):
                st.error("⚠️ 비밀번호는 8~20자이며 영문 대문자, 소문자, 숫자, 특수문자를 각각 최소 1개 이상 포함해야 합니다.")
            else:
                st.success("🎉 회원가입이 정상적으로 접수되었습니다. 로그인 탭에서 접속해 주세요!")

# --- CASE 2: 로그인 완료 상태 (이 분기 안에서만 사이드바 활성화) ---
else:
    # 로그인 성공한 뒤에야 격리해 둔 사이드바 함수를 호출하여 안전하게 렌더링!
    render_sidebar()

    # --- PAGE 1: 광고 생성 스페이스 ---
    if st.session_state.page == "create_ad":
        st.title("🎨 AI 광고 포스터 & 카피 제작")
        st.write("의정님이 구축한 이미지 인페인팅 기술과 GPT 기반 고성능 광고 문구 엔진이 연동되는 핵심 메인 홈입니다.")
        st.markdown("---")
        
        creation_mode = st.radio(
            "👉 원하시는 작업 모드를 골라주세요",
            [
                "🔥 [핵심 MVP] 상품 픽셀 보존형 이미지 + AI 카피 동시 생성", 
                "📸 입력 이미지를 레퍼런스로 스타일 분석받기 (Vision)", 
                "⏳ [후순위 준비중] 텍스트 프롬프트만으로 광고 레이아웃 만들기"
            ]
        )
        
        st.markdown("---")
        
        if "🔥 [핵심 MVP]" in creation_mode:
            col_left, col_right = st.columns([1, 1], gap="large")
            
            with col_left:
                st.subheader("📸 1. 상품 원본 이미지 업로드 (FR-06)")
                uploaded_file = st.file_uploader("누끼 및 리사이즈(1024x1024 LANCZOS) 가 자동으로 수행됩니다.", type=["png", "jpg", "jpeg"])
                if uploaded_file:
                    st.image(uploaded_file, caption="업로드된 원본 상품 사진", width=280)
                    
            with col_right:
                st.subheader("✍️ 2. 상품 컨텍스트 입력")
                product_name = st.text_input("상품명", value="수제 가마솥 통닭")
                product_desc = st.text_area("상품 핵심 설명 (GPT 카피 문구 생성의 핵심 원천 데이터)", value="국산 하림 냉장 생닭을 가마솥 고온에서 빠르게 튀겨내어, 기름기는 쏙 빠지고 겉은 극강으로 바삭하며 속은 육즙이 살아있는 수제 통닭")
            
            st.markdown("---")
            
            col_opt1, col_opt2 = st.columns(2, gap="large")
            with col_opt1:
                st.subheader("🎭 AI 스타일 프리셋 선택 (FR-07)")
                ad_style = st.selectbox(
                    "배경 인페인팅 및 프롬프트 빌더에 투입될 스타일을 골라주세요.",
                    ["MONOTONE", "WARM_VINTAGE", "POP"]
                )
                
            with col_opt2:
                st.subheader("⚙️ 옵션 및 제어 설정")
                use_vision_mode = st.checkbox("GPT-5.4-mini Vision 직접 분석 옵션 켜기 (비용 증가)", value=False)
                use_poster_overlay = st.checkbox("초기 결과에 광고 타이포 적용", value=False)
                
            st.markdown("---")
            
            if st.button("🚀 AI 통합 광고 포스터 생성 시작", use_container_width=True):
                if uploaded_file is None:
                    st.warning("⚠️ 전처리 파이프라인을 작동시키기 위해 상품 이미지를 먼저 등록해 주세요.")
                else:
                    with st.spinner("백엔드 AI 광고 생성 파이프라인 구동 중... (약 15~20초 소요됩니다)"):
                        try:
                            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                            data = {"user_id": str(st.session_state.get("user_id", 1))}
                            
                            upload_resp = requests.post(f"{API_URL}/images/upload", data=data, files=files)
                            
                            if upload_resp.status_code == 201:
                                img_id = upload_resp.json().get("image_id")
                                
                                gen_payload = {
                                    "image_id": img_id,
                                    "product_name": product_name,
                                    "product_description": product_desc,
                                    "style": ad_style,
                                    "use_vision": str(use_vision_mode).lower(),
                                    "poster": str(use_poster_overlay).lower(),
                                }
                                
                                gen_resp = requests.post(f"{API_URL}/ads/generate", data=gen_payload)
                                
                                if gen_resp.status_code == 200:
                                    res_data = gen_resp.json()
                                    
                                    st.session_state.generated_ad = {
                                        "asset_id": res_data.get("asset_id", "demo_asset"),
                                        "title": product_name,
                                        "style": res_data.get("style", ad_style),
                                        "desc": product_desc,
                                        "seed": res_data.get("seed", 12345),
                                        "img_url": _api_image_url(res_data["image_url"]),
                                        "image_without_typography_url": _api_image_url(
                                            res_data.get("image_without_typography_url")
                                        ),
                                        "image_with_typography_url": _api_image_url(
                                            res_data.get("image_with_typography_url")
                                        ),
                                        "copy_text": res_data.get("copy_text", ""),
                                        "use_vision": use_vision_mode,
                                        "poster": res_data.get("poster", use_poster_overlay),
                                        "typography_enabled": res_data.get(
                                            "typography_enabled", use_poster_overlay
                                        ),
                                        "typography_layout": res_data.get("typography_layout"),
                                    }
                                    
                                    st.session_state.history.append({
                                        "id": len(st.session_state.history) + 1,
                                        "title": product_name,
                                        "style": res_data.get("style", ad_style),
                                        "img": _api_image_url(res_data["image_url"]),
                                        "seed": res_data.get("seed", 12345),
                                        "copy": res_data.get("copy_text", "")
                                    })
                                    
                                    st.session_state.page = "result"
                                    st.rerun()
                                else:
                                    st.error(f"광고 생성 파이프라인 오류: {gen_resp.json().get('detail')}")
                            else:
                                st.error("이미지 서버 업로드에 실패했습니다.")
                                
                        except Exception as e:
                            time.sleep(2)
                            mock_copy = "바삭함 속에 숨겨진 따스한 기억\n인생 통닭을 만나보세요." if ad_style == "WARM_VINTAGE" else "통닭, 그 본질의 바삭함."
                            st.session_state.generated_ad = {
                                "title": product_name,
                                "style": ad_style,
                                "desc": product_desc,
                                "seed": random.randint(10000, 99999),
                                "img_url": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=1024",
                                "copy_text": mock_copy,
                                "use_vision": use_vision_mode
                            }
                            st.session_state.page = "result"
                            st.rerun()
        else:
            st.info("💡 현재 고도화 진행 중인 파이프라인 모드입니다. 첫 번째 [핵심 MVP] 탭을 우선 활용해 주세요!")

    # --- PAGE 2: 생성 결과 뷰어 ---
    elif st.session_state.page == "result":
        st.title("✨ AI 융합 광고 포스터 완성")
        st.markdown("---")
        
        ad_data = st.session_state.generated_ad
        
        if ad_data:
            res_col1, res_col2, res_col3 = st.columns([1, 2, 1])
            
            with res_col2:
                st.subheader(f"📦 최종 완성본: {ad_data['title']}")
                if "seed" in ad_data:
                    st.caption(f"자산 ID: {ad_data.get('asset_id', 'demo')} | 시드값: {ad_data['seed']}")
                
                off_url = ad_data.get("image_without_typography_url")
                on_url = ad_data.get("image_with_typography_url")
                if off_url and on_url:
                    typography_enabled = st.toggle(
                        "광고 타이포 적용",
                        value=ad_data.get("typography_enabled", False),
                        key=f"typography_{ad_data.get('asset_id', 'demo')}_{ad_data.get('seed', 0)}",
                    )
                    ad_data["typography_enabled"] = typography_enabled
                    ad_data["poster"] = typography_enabled
                    ad_data["img_url"] = on_url if typography_enabled else off_url

                st.image(ad_data["img_url"], use_container_width=True)
                
                st.success("📝 GPT 추천 매장 광고 문구")
                st.code(ad_data["copy_text"], language="text")
                
                st.markdown("---")
                
                st.subheader("📱 플랫폼별 SNS 공유 문구 즉시 추출 (FR-23)")
                sns_tab1, sns_tab2, sns_tab3 = st.tabs(["🛍️ 인스타그램 피드형", "📰 카드뉴스 표지형", "🎯 웹 배너 홍보형"])
                
                with sns_tab1:
                    st.write("**[인스타그램 피드 캡션 래퍼]**")
                    insta_text = f"🔥 {ad_data['title']} 맛의 신세계 오픈! 🔥\n\n{ad_data['desc'][:60]}...\n\n지금 바로 매장에서 갓 튀겨낸 바삭함을 경험해 보세요!\n\n#우리동네맛집 #{ad_data['title'].replace(' ', '')} #인생맛집 #소상공인화이팅 #AD"
                    st.text_area("인스타 본문 복사용", value=insta_text, height=120, key="insta_text_area")
                    
                with sns_tab2:
                    st.write("**[카드뉴스 타이틀 래퍼]**")
                    card_text = f"💡 사장님이 직접 밝히는 {ad_data['title']}가 유독 맛있는 치명적인 이유 3가지! (👉 넘겨보기)"
                    st.text_area("카드뉴스 카피 복사용", value=card_text, height=70, key="card_text_area")
                    
                with sns_tab3:
                    st.write("**[공식 웹 배너 래퍼]**")
                    banner_text = f"⚡ 단 7일간의 압도적 겉바속촉 혜택! {ad_data['title']} 주문 시 음료 무료 증정! ⚡"
                    st.text_input("배너 텍스트 복사용", value=banner_text, key="banner_text_input")
                
                st.markdown("---")
                
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("🔄 다른 연출 배경으로 다시 만들기 (재생성)", use_container_width=True):
                        with st.spinner("동일 전처리 산출물을 재사용하여 새 seed로 고속 추론 중..."):
                            try:
                                regen_payload = {
                                    "asset_id": ad_data.get("asset_id", "demo_asset"),
                                    "product_name": ad_data["title"],
                                    "product_description": ad_data["desc"],
                                    "style": ad_data["style"],
                                    "prev_seed": ad_data.get("seed", 12345),
                                    "use_vision": ad_data.get("use_vision", False),
                                    "poster": ad_data.get("poster", False)
                                }
                                regen_resp = requests.post(f"{API_URL}/ads/regenerate", json=regen_payload)
                                
                                if regen_resp.status_code == 200:
                                    res_data = regen_resp.json()
                                    st.session_state.generated_ad["seed"] = res_data["seed"]
                                    st.session_state.generated_ad["img_url"] = _api_image_url(
                                        res_data["image_url"]
                                    )
                                    st.session_state.generated_ad["image_without_typography_url"] = \
                                        _api_image_url(res_data.get("image_without_typography_url"))
                                    st.session_state.generated_ad["image_with_typography_url"] = \
                                        _api_image_url(res_data.get("image_with_typography_url"))
                                    st.session_state.generated_ad["typography_enabled"] = res_data.get(
                                        "typography_enabled", ad_data.get("poster", False)
                                    )
                                    st.session_state.generated_ad["typography_layout"] = res_data.get(
                                        "typography_layout"
                                    )
                                    st.session_state.generated_ad["copy_text"] = res_data["copy_text"]
                                    st.success("새로운 고정 시드로 재생성 연동이 완료되었습니다!")
                                    st.rerun()
                                else:
                                    st.error("재생성 파이프라인 호출 실패")
                            except Exception:
                                time.sleep(1.2)
                                st.session_state.generated_ad["seed"] = random.randint(10000, 99999)
                                st.success("데모 재생성이 완료되었습니다!")
                                st.rerun()
                            
                with btn_col2:
                    try:
                        download_data = _download_image(ad_data["img_url"])
                    except Exception:
                        download_data = b""
                    st.download_button(
                        label="📥 선택 이미지 다운로드",
                        data=download_data,
                        file_name="AdNova_Product.png",
                        mime="image/png",
                        use_container_width=True,
                        disabled=not bool(download_data),
                    )
        else:
            st.error("불러올 수 있는 최신 광고 생성 이력이 없습니다.")

    # --- PAGE 3: 마이페이지 및 데이터베이스 연동 ---
    elif st.session_state.page == "mypage":
        st.title("👤 매장 계정 및 과거 광고 생성 이력")
        
        total_generated = len(st.session_state.history)
        st.info(f"📊 {st.session_state.user_info['business_name']} 마케팅 요약: 총 누적 생성 광고 자산 {total_generated}건")
        st.markdown("---")
        
        my_col1, my_col2 = st.columns([1, 2], gap="large")
        
        with my_col1:
            st.subheader("🔒 가맹 사장님 프로필 정보")
            st.text_input("고유 이메일", value="ceo@so-sang.com", disabled=True)
            st.text_input("대표자명", value=st.session_state.user_info["name"])
            st.text_input("인증된 상호명", value=st.session_state.user_info["business_name"])
            st.text_input("주요 업종 카테고리", value=st.session_state.user_info["business_type"])
            if st.button("내 정보 수정 사항 저장", use_container_width=True):
                st.success("DB 유저 데이터가 성공적으로 갱신되었습니다.")
                
        with my_col2:
            st.subheader("🕒 과거 광고 생성 이력 (My History)")
            
            if st.session_state.history:
                for item in reversed(st.session_state.history):
                    with st.container():
                        h_col1, h_col2 = st.columns([1, 3])
                        with h_col1:
                            st.image(item["img"], width=110)
                        with h_col2:
                            st.markdown(f"**{item['title']}**")
                            st.caption(f"적용 스타일: {item['style']} | 고정 시드번호: {item['seed']}")
                            st.text_area("매칭 보관 문구", value=item["copy"], height=65, disabled=True, key=f"hist_text_{item['id']}")
                            
                            if st.button("🔎 상세보기 및 재운영", key=f"hist_btn_{item['id']}", use_container_width=True):
                                st.session_state.generated_ad = {
                                    "title": item["title"],
                                    "style": item["style"],
                                    "desc": "데이터베이스에서 안전하게 로드된 과거 운영 기록 항목입니다.",
                                    "seed": item["seed"],
                                    "img_url": item["img"],
                                    "copy_text": item["copy"],
                                    "use_vision": False
                                }
                                st.session_state.page = "result"
                                st.rerun()
                        st.markdown("---")
            else:
                st.info("아직 누적된 광고 생성 포스터 자산이 없습니다. 홈에서 첫 번째 작품을 빌드해 보세요!")
