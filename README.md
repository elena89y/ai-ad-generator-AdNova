# 🎨 AI Ad Generator (AdNova)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white"/>
  <img src="https://img.shields.io/badge/Streamlit-Frontend-FF4B4B?style=flat-square&logo=streamlit&logoColor=white"/>
  <img src="https://img.shields.io/badge/SDXL-Inpainting-8A2BE2?style=flat-square"/>
  <img src="https://img.shields.io/badge/OpenAI-GPT_API-412991?style=flat-square"/>
  <img src="https://img.shields.io/badge/SQLite-Database-003B57?style=flat-square"/>
  <img src="https://img.shields.io/badge/Docker-Container-2496ED?style=flat-square&logo=docker&logoColor=white"/>
</p>

<p align="center">
  <b>AI8기 고급 프로젝트 | Team AdNova</b><br/>
  AI-powered Advertisement Content Generation Platform
  <br><br>
  유연정(PM) · 김범수 · 정봄 · 한의정
</p>

<p align="center">
  <a href="https://app.notion.com/p/AI8-_-_3-AdNova-2481fffab02c823bbed781ab8fe32242?source=copy_link">📋 협업노트/회의록 & 프로젝트 가이드 </a>
</p>

---

# 📌 프로젝트 개요

소상공인과 온라인 판매자는 상품 홍보를 위해 광고 이미지를 제작해야 하지만, 전문 디자인 툴이나 마케팅 경험이 부족한 경우가 많습니다.

본 프로젝트는 **생성형 AI**를 활용하여 사용자가 업로드한 **상품 이미지**를 기반으로 광고 스타일이 적용된 **광고 이미지**와 **광고 카피**를 자동 생성하는 서비스를 제공합니다.

| 항목        | 내용                                                |
| ----------- | --------------------------------------------------- |
| 프로젝트명  | AI Ad Generator                                     |
| 대상 사용자 | 소상공인, 자영업자, 온라인 셀러, 마케터             |
| 기간        | 2026.07.01 ~ 2026.07.30                             |
| 핵심 기능   | 상품 이미지 기반 광고 이미지 생성 및 광고 카피 생성 |

---

# 📷 Demo

## Login

(이미지)

---

## Advertisement Generation

(이미지)

---

## Result

(이미지)

---

# ✨ 주요 기능

- 🔐 회원가입 및 로그인 (bcrypt + JWT)
- 🖼 상품 이미지 업로드
- ✨ 상품 이미지 전처리 (배경 제거 · 리사이즈 · 품질 보정)
- 🎨 광고 스타일 결정 — 2경로 (AI 추천 후보 선택 / 자유 텍스트 입력)
- 🤖 AI 광고 이미지 생성 (제품 보존 + 배경 교체)
- 📝 AI 광고 카피 생성 (생성된 광고 이미지 기반)
- 🔄 광고 재생성
- 📂 생성 이력 관리
- 📤 SNS 공유용 Export

---

# 🗂️ 프로젝트 구조

```text
ai-ad-generator-AdNova/
├── .gitignore
├── README.md
├── docker-compose.yml
├── .env.example
│
├── frontend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── main.py
│       ├── pages/
│       │   ├── login.py
│       │   ├── signup.py
│       │   ├── generate.py
│       │   └── history.py
│       ├── components/
│       │   ├── sidebar.py
│       │   ├── upload_box.py
│       │   └── result_card.py
│       └── utils/
│           └── api_client.py
│
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── uploads/
    │   └── .gitkeep
    ├── processed/
    │   └── .gitkeep
    ├── results/
    │   └── .gitkeep
    └── app/
        ├── main.py
        ├── core/
        │   ├── config.py
        │   └── security.py
        ├── database/
        │   ├── connection.py
        │   └── models.py
        ├── schemas/
        │   ├── auth.py
        │   ├── image.py
        │   └── ads.py
        ├── api/
        │   ├── auth.py
        │   ├── images.py
        │   ├── ads.py
        │   ├── copy.py
        │   ├── history.py
        │   └── export.py
        └── services/
            ├── image_service.py
            ├── gpt_service.py
            ├── prompt_service.py
            └── history_service.py
```

---

# 🛠 기술 스택

| 구성 요소      | 기술                                       |
| -------------- | ------------------------------------------ |
| Backend        | FastAPI                                    |
| Frontend       | Streamlit                                  |
| Authentication | JWT + bcrypt                               |
| AI Preprocess  | rembg (u2net, ONNX / GPU 가속)             |
| AI Image       | SDXL Inpainting (diffusers, GCP L4)        |
| AI Copy        | OpenAI GPT (Vision / BLIP 캡셔닝)          |
| Database       | SQLite                                     |
| Deployment     | Docker + GCP                               |

---

# 🚀 실행 방법

### 환경 설치

```bash
git clone https://github.com/elena89y/ai-ad-generator-AdNova.git

cd ai-ad-generator-AdNova

pip install -r requirements.txt
```

### 환경 변수

```
OPENAI_API_KEY=xxxxxxxx
```

### 실행

```bash
uvicorn app.main:app --reload
```

또는

```bash
streamlit run app.py
```

---

# 🧩 서비스 구조 (4단계 파이프라인)

```text
상품 이미지 업로드
        │
        ▼
① 이미지 전처리 (FR-06)
   배경 제거(rembg) · 리사이즈 · 품질 보정 · 제품 마스크 생성
        │
        ▼
② 광고 스타일 결정 — 2경로 (FR-05)
   경로1: Vision 분석 → 스타일 후보 3개 추천 → 유저 선택
   경로2: 유저 자유 텍스트 입력 → 스타일 결정
        │
        ▼
   Prompt Builder (FR-07)
   상품 정보 + 스타일 → positive/negative 프롬프트
        │
        ▼
③ 광고 이미지 생성 (FR-08)
   SDXL Inpainting — 제품 보존(마스크) + 배경 교체
        │
        ▼
④ 광고 카피 생성 (FR-09)
   생성된 광고 이미지 기반 — BLIP 캡션(저비용) / Vision(검증·데모)
        │
        ▼
최종 광고 콘텐츠 (이미지 + 카피)
```

> 스타일(문구 톤·색상: 모노톤/웜빈티지/팝)과 용도(채널·목적: SNS/카드뉴스/배너/상세페이지/전단지)는
> 별개 축으로 분리되어 있습니다. 자세한 실험 기록은 실험로그 문서를 참조하세요.

---

# 📡 API

| Method | Endpoint        | 설명               |
| ------ | --------------- | ------------------ |
| POST   | /auth/signup    | 회원가입           |
| POST   | /auth/login     | 로그인             |
| POST   | /auth/logout    | 로그아웃           |
| POST   | /images/upload  | 상품 이미지 업로드 |
| POST   | /images/process | 상품 이미지 전처리 |
| POST   | /ads/style      | 광고 스타일 결정 (경로1: AI 추천 / 경로2: 자유 입력) |
| POST   | /ads/generate   | 광고 이미지 생성   |
| POST   | /ads/regenerate | 광고 재생성        |
| POST   | /copy/generate  | 광고 문구 생성     |
| GET    | /history        | 생성 이력 조회     |
| POST   | /export/sns     | SNS 공유용 Export  |

---

# 👥 Team AdNova

| 이름             | 역할                                                                                    |
| ---------------- | --------------------------------------------------------------------------------------- |
| **유연정** | **Project Manager (PM)**Backend (FastAPI / API)DevOps (Docker / GCP / Deployment) |
| **김범수** | Backend (FastAPI / API)DevOps (Docker / GCP / Deployment)                               |
| **한의정** | AI Model / Prompt Engineering                                                           |
| **정봄**   | Frontend (Streamlit / UI·UX)                                                           |

---

# 📎 참고 자료

- [📋 협업 노트 (Notion)](https://app.notion.com/p/Daily-Logs-b201fffab02c8269a55c01286e7eed21?source=copy_link)
- [📋 회의록 (Notion)](https://app.notion.com/p/Daily-Logs-b201fffab02c8269a55c01286e7eed21?source=copy_link)
- [고급프로젝트 가이드라인](https://app.notion.com/p/AI8-_-_3-AdNova-2481fffab02c823bbed781ab8fe32242?source=copy_link)
- [📄 최종 발표 자료]()
- [📚 OpenAI API Documentation]()
- [📚 FastAPI Documentation]()
- [📚 Streamlit Documentation]()


---

<p align="center">
  <sub>AI8기 고급 프로젝트 | 2026 · Team AdNova</sub>
</p>
