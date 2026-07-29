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

기존 systemd 백엔드가 사용하는 SQLite와 이미지 파일이 있다면, Docker 전환 전에 한 번만 이전한다.

```bash
cd ~/ai-ad-generator-AdNova
mkdir -p runtime/data/uploads runtime/results
cp -a backend/data/app.db runtime/data/app.db
cp -a backend/data/admin.db runtime/data/admin.db
cp -a backend/uploads/. runtime/data/uploads/

sudo python3 backend/app/scripts/migrate_docker_results.py \
  --database runtime/data/app.db \
  --source backend/results \
  --destination runtime/results \
  --dry-run

sudo python3 backend/app/scripts/migrate_docker_results.py \
  --database runtime/data/app.db \
  --source backend/results \
  --destination runtime/results
```

결과 이미지 마이그레이션은 DB를 자동 백업한 뒤, DB에 연결된 기존 생성 이미지만
`runtime/results/`로 복사하고 `images.file_path`를 컨테이너 경로인
`/app/results/`로 변경한다. 파일이 없는 행과 업로드 이미지 경로는 변경하지 않는다.

이미 `runtime/`에 운영 데이터가 있다면 DB와 업로드 파일 복사 명령은 다시 실행하지
않는다. 기존 결과 이미지 경로만 남아 있다면 마이그레이션 명령의 드라이런 결과를
확인한 뒤 한 번 실행한다. 마이그레이션 중에는 웹 백엔드가 DB를 변경하지 않도록
`docker compose down` 또는 `docker compose stop backend-web` 상태를 유지한다.

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

현재 Compose는 기본적으로 `GENERATION_SERVICE_URL=http://host.docker.internal:8100`
을 사용한다. 호스트 systemd 생성 서버가 `127.0.0.1`에만 바인딩되어 있으면 Docker
백엔드에서 접근할 수 없으므로, 8100 연결 방식을 준비하기 전에는 광고 생성 요청이
실패한다. 일반 로그인·조회 API와 8100 생성 서버는 독립적으로 운영한다.

## systemd 생성 워커 연결

Docker 백엔드가 호스트의 생성 워커에 접근할 수 있도록 저장소의 systemd 서비스
설정을 VM에 반영한다. 워커는 Docker 브리지에서 접근할 수 있도록
`0.0.0.0:8100`에 바인딩하지만, 8100은 GCP 및 호스트 방화벽에서 외부에 공개하지
않는다.

```bash
cd ~/ai-ad-generator-AdNova
sudo cp backend/deploy/systemd/adnova-generation.service \
  /etc/systemd/system/adnova-generation.service
sudo systemctl daemon-reload
sudo systemctl restart adnova-generation
```

모델 사전 로딩 때문에 워커 준비에는 몇 분이 걸릴 수 있다. 다음 세 단계가 모두
성공한 뒤 광고 생성을 테스트한다.

```bash
sudo systemctl status adnova-generation --no-pager
curl -i http://127.0.0.1:8100/health
sudo docker compose exec backend-web python3 -c \
  "import requests; print(requests.get('http://host.docker.internal:8100/health', timeout=10).json())"
```

`ss -ltnp`에서 8100이 모든 인터페이스에 바인딩된 것은 Docker 접근을 위한 설정이다.
Nginx에는 8100 프록시를 추가하지 않고, GCP 인바운드 방화벽에도 8100 허용 규칙을
추가하지 않는다.

## main 자동 배포

최종 운영은 `main`만 자동 배포한다. 기존 `adnova-autodeploy.timer`는 systemd
백엔드와 프론트를 다시 실행하므로 Docker 전환 후에는 사용하지 않는다.

`main`에 자동 배포 파일이 병합된 뒤 VM에 설치한다.

```bash
cd ~/ai-ad-generator-AdNova

sudo systemctl disable --now adnova-autodeploy.timer
sudo install -m 0755 deploy/docker/adnova-docker-autodeploy.sh \
  /usr/local/sbin/adnova-docker-autodeploy
sudo install -m 0644 deploy/docker/adnova-docker-autodeploy.service \
  /etc/systemd/system/adnova-docker-autodeploy.service
sudo install -m 0644 deploy/docker/adnova-docker-autodeploy.timer \
  /etc/systemd/system/adnova-docker-autodeploy.timer

sudo systemctl daemon-reload
sudo systemctl enable --now adnova-docker-autodeploy.timer
```

타이머는 5분 간격으로 `upstream/main`을 확인한다. 새 커밋이 있을 때만
fast-forward로 갱신하고, Docker 이미지를 빌드한 뒤 프론트·백엔드·생성 워커 health를
확인한다. VM 작업 트리에 수정 또는 미추적 파일이 있거나 브랜치가 갈라진 경우에는
파일을 덮어쓰지 않고 배포를 중단한다. health 확인까지 성공한 커밋만 별도로
기록하므로, 빌드 또는 실행이 실패한 커밋은 다음 타이머 실행에서 다시 시도한다.

설치 직후 수동으로 한 번 실행해 확인할 수 있다.

```bash
sudo systemctl start adnova-docker-autodeploy.service
sudo systemctl status adnova-docker-autodeploy.service --no-pager
sudo journalctl -u adnova-docker-autodeploy.service -n 100 --no-pager
sudo systemctl list-timers adnova-docker-autodeploy.timer --no-pager
```

컨테이너의 `restart: unless-stopped`와 Docker·Nginx·생성 워커의 systemd 자동 시작이
24시간 서비스 유지를 담당하고, 이 타이머는 `main`의 새 코드 반영만 담당한다.

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
