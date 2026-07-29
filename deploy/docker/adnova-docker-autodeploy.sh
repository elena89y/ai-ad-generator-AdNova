#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${ADNOVA_REPO_DIR:-/home/spai0803/ai-ad-generator-AdNova}"
DEPLOY_USER="${ADNOVA_DEPLOY_USER:-spai0803}"
REMOTE="${ADNOVA_DEPLOY_REMOTE:-upstream}"
BRANCH="${ADNOVA_DEPLOY_BRANCH:-main}"
LOCK_FILE="/run/lock/adnova-docker-autodeploy.lock"
STATE_DIR="/var/lib/adnova-docker-autodeploy"
LAST_SUCCESS_FILE="${STATE_DIR}/last-successful-commit"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "다른 Docker 배포가 진행 중이므로 이번 실행을 건너뜁니다."
  exit 0
fi

if [[ ! -d "${REPO_DIR}/.git" || ! -f "${REPO_DIR}/docker-compose.yml" ]]; then
  echo "AdNova 저장소를 찾을 수 없습니다: ${REPO_DIR}" >&2
  exit 1
fi

git_as_deploy_user() {
  runuser -u "${DEPLOY_USER}" -- git -C "${REPO_DIR}" "$@"
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local attempts="${3:-60}"

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl -fsS --max-time 5 "${url}" >/dev/null; then
      echo "${name} 확인 완료: ${url}"
      return 0
    fi
    sleep 2
  done

  echo "${name} health 확인 실패: ${url}" >&2
  return 1
}

cd "${REPO_DIR}"

if [[ -n "$(git_as_deploy_user status --porcelain --untracked-files=normal)" ]]; then
  echo "VM 작업 트리에 변경사항이 있어 자동 배포를 중단합니다." >&2
  git_as_deploy_user status --short >&2
  exit 1
fi

git_as_deploy_user fetch --prune "${REMOTE}" "${BRANCH}"

if git_as_deploy_user show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git_as_deploy_user switch "${BRANCH}"
else
  git_as_deploy_user switch --track -c "${BRANCH}" "${REMOTE}/${BRANCH}"
fi

current_commit="$(git_as_deploy_user rev-parse HEAD)"
target_commit="$(git_as_deploy_user rev-parse "${REMOTE}/${BRANCH}")"
last_successful_commit=""
if [[ -f "${LAST_SUCCESS_FILE}" ]]; then
  last_successful_commit="$(<"${LAST_SUCCESS_FILE}")"
fi

if [[ "${current_commit}" == "${target_commit}" &&
      "${last_successful_commit}" == "${target_commit}" ]]; then
  echo "${BRANCH}에 새 커밋이 없습니다."
  exit 0
fi

if [[ "${current_commit}" != "${target_commit}" ]]; then
  if ! git_as_deploy_user merge-base --is-ancestor \
    "${current_commit}" "${target_commit}"; then
    echo "로컬 ${BRANCH}와 ${REMOTE}/${BRANCH}가 갈라져 자동 배포를 중단합니다." >&2
    exit 1
  fi

  git_as_deploy_user merge --ff-only "${target_commit}"
else
  echo "직전 배포가 완료되지 않아 ${target_commit} 배포를 다시 시도합니다."
fi

docker compose config -q
docker compose build backend-web frontend
docker compose up -d backend-web frontend

wait_for_http "FastAPI" "http://127.0.0.1:8000/health"
wait_for_http "Next.js" "http://127.0.0.1:3000/"
wait_for_http "생성 워커" "http://127.0.0.1:8100/health" 210

install -d -m 0750 "${STATE_DIR}"
printf '%s\n' "${target_commit}" >"${LAST_SUCCESS_FILE}.tmp"
mv "${LAST_SUCCESS_FILE}.tmp" "${LAST_SUCCESS_FILE}"

echo "Docker 자동 배포 완료: ${current_commit} -> ${target_commit}"
