# Docker 웹 배포 안내

이 구성은 기존 VM의 Nginx와 HTTPS 설정은 유지하고, Next.js와 FastAPI만 Docker Compose로 실행한다.
GPU 생성 서버(8100)는 기존 systemd 서비스 또는 별도 GPU 컨테이너로 유지한다.

## 영구 데이터

`runtime/`은 Git에 포함되지 않으며 다음 데이터를 보관한다.

- `runtime/data/app.db`: 일반 사용자 DB
- `runtime/data/admin.db`: 관리자 인증 DB
- `runtime/data/uploads/`: 업로드 이미지
- `runtime/results/`: 생성 결과 이미지

컨테이너를 재생성해도 이 경로는 VM 디스크에 남는다. `runtime/`을 삭제하면 DB와 이미지도 함께 삭제되므로 삭제하지 않는다.

## 최초 실행

기존 systemd 백엔드가 사용하는 SQLite와 이미지 파일이 있다면, Docker 전환 전에 한 번만 복사한다.

```bash
cd ~/ai-ad-generator-AdNova
mkdir -p runtime/data/uploads runtime/results
cp -a backend/data/app.db runtime/data/app.db
cp -a backend/data/admin.db runtime/data/admin.db
cp -a backend/uploads/. runtime/data/uploads/
cp -a backend/results/. runtime/results/
```

이미 `runtime/`에 운영 데이터가 있다면 위 복사 명령은 다시 실행하지 않는다.

이미지와 DB를 준비한 뒤 컨테이너 이미지를 빌드한다.

```bash
cd ~/ai-ad-generator-AdNova
docker compose build backend-web frontend
```

8000 포트를 기존 `adnova.service`가 사용하므로, 실제 전환 시에는 systemd 백엔드를 먼저 멈춘다. GPU 생성 서비스 `adnova-generation.service`는 이 단계에서 건드리지 않는다.

```bash
sudo systemctl stop adnova
docker compose up -d backend-web frontend
docker compose ps
curl -i http://127.0.0.1:8000/health
curl -I http://127.0.0.1:3000
```

`backend/.env`에는 배포용 OAuth, SMTP, JWT, CORS 설정을 유지한다. Compose가 DB와 업로드 경로만 컨테이너 경로로 덮어쓴다.

현재 Compose의 기본값은 웹 기능을 먼저 안정화하기 위해 `GENERATION_SERVICE_URL`을 비운 상태다. 호스트 systemd의 8100 생성 서버를 Docker 백엔드와 연결하는 작업은 GPU 네트워크 접근 방식을 정한 뒤 별도로 진행한다.

## Nginx 연결

기존 도메인용 Nginx `server` 블록에 `deploy/nginx/adnova-docker.locations.conf`의 두 `location` 블록을 넣는다.

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 확인 및 로그

```bash
docker compose logs -f backend-web
docker compose logs -f frontend
docker compose ps
```

## 주의

- 일반 웹 배포에서는 8100 생성 서버 포트를 외부에 열지 않는다.
- Docker 백엔드와 기존 `adnova.service`를 동시에 실행하지 않는다. 되돌릴 때는 `docker compose down` 후 `sudo systemctl start adnova`를 실행한다.
- `docker compose down -v`는 Docker 볼륨을 지우는 명령이지만, 현재 구성의 데이터는 `runtime/` 바인드 마운트에 있으므로 직접 삭제하지 않는 한 남는다.
- GPU 워커는 NVIDIA Container Toolkit과 모델 캐시 경로를 별도로 확인한 뒤 활성화한다.
