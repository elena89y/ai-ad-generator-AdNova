#!/usr/bin/env bash
set -euo pipefail

# Share one Hugging Face token on the VM without putting it in git, venv, or /etc/environment.
# Source token must already exist for the current AI owner account.

GROUP_NAME="adnova-models"
SOURCE_TOKEN="${SOURCE_TOKEN:-/home/spai0820/.cache/huggingface/token}"
SECRET_DIR="/opt/adnova/secrets"
SECRET_TOKEN="${SECRET_DIR}/hf_token"
PROFILE="/etc/profile.d/adnova-hf-cache.sh"

if [ ! -s "${SOURCE_TOKEN}" ]; then
  echo "ERROR: source HF token missing: ${SOURCE_TOKEN}" >&2
  exit 1
fi

if ! getent group "${GROUP_NAME}" >/dev/null; then
  groupadd "${GROUP_NAME}"
fi

mkdir -p "${SECRET_DIR}"
cp "${SOURCE_TOKEN}" "${SECRET_TOKEN}"
chown root:"${GROUP_NAME}" "${SECRET_DIR}" "${SECRET_TOKEN}"
chmod 750 "${SECRET_DIR}"
chmod 640 "${SECRET_TOKEN}"

cat >"${PROFILE}" <<'EOF'
# AdNova shared model cache and shared Hugging Face token path.
# Model blobs/snapshots are shared; the token is stored once in /opt/adnova/secrets.
# Do not export HF_TOKEN directly: `env | grep HF` would reveal the secret value.
export HF_HUB_CACHE=/opt/adnova/models/hub
export U2NET_HOME=/opt/adnova/models/u2net
export HF_TOKEN_PATH=/opt/adnova/secrets/hf_token
EOF
chmod 644 "${PROFILE}"

# Keep non-secret paths in /etc/environment. Never store HF_TOKEN there.
if grep -q "^HF_HUB_CACHE=" /etc/environment 2>/dev/null; then
  sed -i "s#^HF_HUB_CACHE=.*#HF_HUB_CACHE=/opt/adnova/models/hub#" /etc/environment
else
  printf "\nHF_HUB_CACHE=/opt/adnova/models/hub\n" >>/etc/environment
fi

if grep -q "^U2NET_HOME=" /etc/environment 2>/dev/null; then
  sed -i "s#^U2NET_HOME=.*#U2NET_HOME=/opt/adnova/models/u2net#" /etc/environment
else
  printf "U2NET_HOME=/opt/adnova/models/u2net\n" >>/etc/environment
fi

if grep -q "^HF_TOKEN_PATH=" /etc/environment 2>/dev/null; then
  sed -i "s#^HF_TOKEN_PATH=.*#HF_TOKEN_PATH=${SECRET_TOKEN}#" /etc/environment
else
  printf "HF_TOKEN_PATH=%s\n" "${SECRET_TOKEN}" >>/etc/environment
fi
sed -i "/^HF_TOKEN=/d" /etc/environment

echo "Shared HF token configured:"
ls -ld "${SECRET_DIR}"
ls -l "${SECRET_TOKEN}" | awk '{print $1, $3, $4, $9}'
echo "TOKEN_BYTES=$(wc -c < "${SECRET_TOKEN}")"
echo "PROFILE=${PROFILE}"
