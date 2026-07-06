import streamlit as st
import requests
import random
import time

# 1. 페이지 기본 설정 및 초기 사이드바 접힘 상태 적용
st.set_page_config(
    page_title="AdNova - 소상공인 AI 광고 제작소", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 백엔드 API 서버 주소 (서버 기동 환경에 맞게 조절)
API_URL = "http://localhost:8000"

# 2. 세션 상태(Session State) 초기화
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "page" not in st.session_state:
    st.session_state.page = "create_ad"
if "user_info" not in st.session_state:
    st.session_state.user_info = {"name": "소상공인", "business_name": "우리동네 가게", "business_type": "음식점"}
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "generated_ad" not in st.session_state:
    st.session_state.generated_ad = None
if "history" not in st.session_state:
    st.session_state.history = [
        {"id": 1, "title": "바삭한 가마솥 통닭", "style": "WARM_VINTAGE", "img": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=500", "seed": 12345, "copy": "추억을 튀기는 가마솥 통닭\n아버지가 퇴근길에 사오시던 그 맛 그대로."},
        {"id": 2, "title": "모던 미니멀 조명", "style": "MONOTONE", "img": "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=500", "seed": 67890, "copy": "공간을 채우는 절제의 미학\n빛, 그 본질에 집중하다."}
    ]

# --- 화면 1: 로그인 / 회원가입 ---
if not st.session_state.logged_in:
    st.title("🔑 AdNova 로그인")
    st.write("소상공인을 위한 스마트한 AI 광고 사진 및 문구 제작소에 오신 것을 환영합니다.")
    
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    
    with tab1:
        login_email = st.text_input("이메일 주소", value="ceo@so-sang.com", key="login_email")
        login_pw = st.text_input("비밀번호", type="password", value="Password123!", key="login_pw")
        
        if st.button("로그인하기", use_container_width=True):
            # 백엔드 auth.py UserLogin 대응 데이터 구조
            payload = {"email": login_email, "password": login_pw}
            try:
                # [실제 연동 시 주석 해제]
                # response = requests.post(f"{API_URL}/auth/login", json=payload)
                # if response.status_code == 200:
                #     data = response.json()
                #     st.session_state.logged_in = True
                #     st.session_state.access_token = data["access_token"]
                #     st.session_state.user_info = data["user"]
                #     st.rerun()
                
                # 테스트/데모용 폴백 작동
                st.session_state.logged_in = True
                st.session_state.user_info = {
                    "name": "Bom", 
                    "business_name": "봄봄 푸드", 
                    "business_type": "요식업"
                }
                st.success(f"🎉 {st.session_state.user_info['name']} 사장님, 반갑습니다!")
                time.sleep(0.5)
                st.rerun()
            except Exception:
                st.error("서버 연결에 실패했습니다. 데모 모드로 진입합니다.")
                st.session_state.logged_in = True
                st.rerun()
                
    with tab2:
        st.subheader("새로운 회원가입")
        reg_email = st.text_input("이메일 주소", placeholder="example@email.com")
        reg_id = st.text_input("아이디 (7~12자 영문/숫자)", placeholder="bomspring12")
        reg_pw = st.text_input("비밀번호 (8~20자, 대소문자/숫자/특수문자 필수 포함)", type="password")
        reg_name = st.text_input("사장님 이름")
        reg_bname = st.text_input("상호명")
        reg_btype = st.selectbox("업종 선택", ["요식업", "의류/패션", "뷰티/미용", "카페/디저트", "기타 소매업"])
        
        if st.button("회원가입 완료", use_container_width=True):
            # 백엔드 backend/app/schemas/auth.py 정규식 검증 규칙 프론트단 적용
            import re
            id_pattern = r"^[A-Za-z0-9]{7,12}$"
            pw_pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&^#()_\-+=])[A-Za-z\d@$!%*?&^#()_\-+=]{8,20}$"
            
            if not re.match(id_pattern, reg_id):
                st.error("⚠️ 아이디는 영문과 숫자만 사용할 수 있으며 7~12자여야 합니다.")
            elif not re.match(pw_pattern, reg_pw):
                st.error("⚠️ 비밀번호는 8~20자이며 영문 대문자, 소문자, 숫자, 특수문자를 각각 최소 1개 이상 포함해야 합니다.")
            else:
                st.success("🎉 회원가입이 정상적으로 접수되었습니다. 로그인 탭에서 접속해 주세요!")

# --- 메인 대시보드 인프라 (로그인 후 상태) ---
else:
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
                    ["WARM_VINTAGE (따뜻하고 감성적인 레트로 카페 무드)", "MONOTONE (미니멀하고 세련된 스튜디오 모던 스타일)", "POP (통통 튀고 화려한 원색조 팝아트 느낌)"]
                )
                
            with col_opt2:
                st.subheader("⚙️ 문구 생성 옵션 (FR-09)")
                use_vision_mode = st.checkbox("GPT-5.4-mini Vision 직접 분석 옵션 켜기", value=False, help="체크 해제 시 BLIP 로컬 캡셔닝 기반 저비용 경로로 구동되며, 체크 시 생성 이미지를 직접 분석하여 품질이 극대화됩니다.")
                
            st.markdown("---")
            
            if st.button("🚀 AI 통합 광고 포스터 생성 시작", use_container_width=True):
                if uploaded_file is None:
                    st.warning("⚠️ 전처리 파이프라인을 작동시키기 위해 상품 이미지를 먼저 등록해 주세요.")
                else:
                    with st.spinner("의정님의 파이프라인 구동 중: 1단계 전처리 및 누끼 마스킹 → 2단계 SDXL Inpainting 실행 → 3단계 GPT 문구 추출 중... (약 8초 소요)"):
                        time.sleep(2.5) # 엔진 로딩 연출
                        
                        style_preset = ad_style.split(" ")[0]
                        sample_seed = random.randint(10000, 99999)
                        
                        # 백엔드 gpt_service.py의 _STYLE_TONE 문구 로직 연동 모사
                        if style_preset == "WARM_VINTAGE":
                            mock_copy = "바삭함 속에 숨겨진 따스한 기억\n그 시절 아버지가 건네시던 인생 통닭을 만나보세요."
                        elif style_preset == "MONOTONE":
                            mock_copy = "통닭, 그 본질의 바삭함.\n어떤 수식어도 필요 없는 완벽한 육즙의 조화."
                        else:
                            mock_copy = "입안에서 터지는 바삭 바삭 폭탄!\n오늘 스트레스는 대폭발 크리스피 통닭으로 날려버려!"
                        
                        # 생성 데이터 적재
                        st.session_state.generated_ad = {
                            "title": product_name,
                            "style": style_preset,
                            "desc": product_desc,
                            "seed": sample_seed,
                            "img_url": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=1024", # 고화질 소스 연동
                            "copy_text": mock_copy,
                            "use_vision": use_vision_mode
                        }
                        
                        # 마이페이지 연동용 히스토리 모델 테이블에 인서트 시뮬레이션
                        st.session_state.history.append({
                            "id": len(st.session_state.history) + 1,
                            "title": product_name,
                            "style": style_preset,
                            "img": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=500",
                            "seed": sample_seed,
                            "copy": mock_copy
                        })
                        
                        st.session_state.page = "result"
                        st.rerun()
        else:
            st.info("💡 현재 고도화 진행 중인 파이프라인 모드입니다. 첫 번째 [핵심 MVP] 탭을 우선 활용해 주세요!")

    # --- PAGE 2: 생성 결과 뷰어 및 다운로드/재생성 스페이스 ---
    elif st.session_state.page == "result":
        st.title("✨ AI 융합 광고 포스터 완성")
        st.write("원본 픽셀 재합성(Post-composite) 보존율 기술과 GPT 문구 매칭 모델이 결합된 고품질 인쇄 규격 결과물입니다.")
        st.markdown("---")
        
        ad_data = st.session_state.generated_ad
        
        if ad_data:
            res_col1, res_col2, res_col3 = st.columns([1, 2, 1])
            
            with res_col2:
                st.subheader(f"📦 최종 완성본: {ad_data['title']}")
                st.caption(f"인페인팅 모델: SDXL 1.0 | 시드값: {ad_data['seed']} | 문구 엔진: GPT-5.4-mini")
                
                # 메인 광고 결과물 출력
                st.image(ad_data["img_url"], use_container_width=True)
                
                # 이미지 기반 생성 문구 분할 렌더링 (FR-09)
                st.success("📝 GPT 추천 매장 광고 문구 (헤드라인 및 서브카피)")
                st.code(ad_data["copy_text"], language="text")
                
                st.markdown("---")
                
                # 소상공인 마케팅 지원을 위한 확장 기능: SNS 채널용 문구 다중 탭 연동 (FR-23)
                st.subheader("📱 플랫폼별 SNS 공유 문구 즉시 추출 (FR-23)")
                sns_tab1, sns_tab2, sns_tab3 = st.tabs(["🛍️ 인스타그램 피드형", "📰 카드뉴스 표지형", "🎯 웹 배너 홍보형"])
                
                with sns_tab1:
                    st.write("**[인스타그램 피드 캡션 래퍼]**")
                    insta_text = f"🔥 {ad_data['title']} 맛의 신세계 오픈! 🔥\n\n{ad_data['desc'][:60]}...\n\n지금 바로 매장에서 갓 튀겨낸 바삭함을 경험해 보세요!\n\n#우리동네맛집 #{ad_data['title'].replace(' ', '')} #인생맛집 #소상공인화이팅 #AD"
                    st.text_area("인스타 본문 복사용", value=insta_text, height=120)
                    
                with sns_tab2:
                    st.write("**[카드뉴스 타이틀 래퍼]**")
                    card_text = f"💡 사장님이 직접 밝히는 {ad_data['title']}가 유독 맛있는 치명적인 이유 3가지! (👉 넘겨보기)"
                    st.text_area("카드뉴스 카피 복사용", value=card_text, height=70)
                    
                with sns_tab3:
                    st.write("**[공식 웹 배너 래퍼]**")
                    banner_text = f"⚡ 단 7일간의 압도적 겉바속촉 혜택! {ad_data['title']} 주문 시 음료 무료 증정! ⚡"
                    st.text_input("배너 텍스트 복사용", value=banner_text)
                
                st.markdown("---")
                
                # 조작 제어 버튼 레이아웃
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    # FR-12: 새 시드값 기반 동일 조건 재생성 파이프라인 트리거
                    if st.button("🔄 다른 연출 배경으로 다시 만들기 (재생성)", use_container_width=True):
                        with st.spinner("동일 입력 데이터 조건을 계승하고, 백엔드 seed 파라미터만 변경하여 인페인팅 재추론 중..."):
                            time.sleep(1.5)
                            st.session_state.generated_ad["seed"] = random.randint(10000, 99999)
                            st.success("새로운 고정 시드로 재생성 연동이 완료되었습니다!")
                            st.rerun()
                            
                with btn_col2:
                    st.download_button(
                        label="📥 마케팅용 원본 이미지 다운로드",
                        data=b"mock_image_bytes",
                        file_name=f"AdNova_Product_{ad_data['seed']}.png",
                        mime="image/png",
                        use_container_width=True
                    )
        else:
            st.error("불러올 수 있는 최신 광고 생성 이력이 없습니다. 제작 홈에서 생성을 진행해 주세요.")

    # --- PAGE 3: 마이페이지 및 데이터베이스 연동 관리 스페이스 ---
    elif st.session_state.page == "mypage":
        st.title("👤 매장 계정 및 과거 광고 생성 이력")
        st.write("데이터베이스의 `users`, `images`, `advertisements` 테이블과 싱크되어 보관 중인 마케팅 산출물 자산 목록입니다.")
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
            st.write("이전에 생성했던 포스터 목록입니다. [상세보기 및 재운영]을 클릭하시면 결과 창으로 연동되어 다시 다운로드 및 채널별 카피 확인이 가능합니다.")
            
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
                            
                            # 과거 데이터 상태 복원 트리거
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