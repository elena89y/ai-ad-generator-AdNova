#!/usr/bin/env bash
set -euo pipefail

# AdNova VM infra helper:
# Share Hugging Face model blobs/snapshots across Linux users.
#
# Why HF_HUB_CACHE instead of HF_HOME:
# - HF_HOME can contain token files.
# - HF_HUB_CACHE points only to downloaded model cache data.
# - Token sharing, when needed, is configured separately by setup_shared_hf_token.sh
#   via HF_TOKEN_PATH so `env | grep HF` never prints the secret value.

GROUP_NAME="adnova-models"
BASE_DIR="/opt/adnova"
HF_HUB_DIR="${BASE_DIR}/models/hub"
U2NET_DIR="${BASE_DIR}/models/u2net"

if ! getent group "${GROUP_NAME}" >/dev/null; then
  groupadd "${GROUP_NAME}"
fi

mkdir -p "${HF_HUB_DIR}" "${U2NET_DIR}" "${BASE_DIR}/cache" "${BASE_DIR}/outputs"
chgrp -R "${GROUP_NAME}" "${BASE_DIR}"

# Existing project users on this VM. Missing users are skipped.
for user in spai0307 spai0610 spai0612 spai0301 spai0637 spai0820 spai0807 spai0816 spai0803 colourxswitch; do
  if id "${user}" >/dev/null 2>&1; then
    usermod -aG "${GROUP_NAME}" "${user}"
  fi
done

# Team members may have existing sessions before group membership refresh.
# Model weights are not secrets, so make the shared cache broadly readable/writable.
chmod -R a+rwX "${BASE_DIR}/models" "${BASE_DIR}/cache" "${BASE_DIR}/outputs"
find "${BASE_DIR}" -type d -exec chmod 2775 {} +

# rembg stores ONNX segmentation models outside Hugging Face cache, traditionally in ~/.u2net.
# Copy existing model files into a shared location. Do not copy credentials or delete user caches.
for user_home in /home/spai*/.u2net /home/colourxswitch/.u2net; do
  if [ -d "${user_home}" ]; then
    rsync -a "${user_home}/" "${U2NET_DIR}/"
  fi
done
chgrp -R "${GROUP_NAME}" "${U2NET_DIR}"
chmod -R a+rwX "${U2NET_DIR}"
find "${U2NET_DIR}" -type d -exec chmod 2775 {} +

cat >/etc/profile.d/adnova-hf-cache.sh <<EOF
# AdNova shared Hugging Face model cache.
# This file exports paths only; do not export HF_TOKEN here.
export HF_HUB_CACHE=${HF_HUB_DIR}
export U2NET_HOME=${U2NET_DIR}
EOF
chmod 644 /etc/profile.d/adnova-hf-cache.sh

if grep -q "^HF_HUB_CACHE=" /etc/environment 2>/dev/null; then
  sed -i "s#^HF_HUB_CACHE=.*#HF_HUB_CACHE=${HF_HUB_DIR}#" /etc/environment
else
  printf "\nHF_HUB_CACHE=%s\n" "${HF_HUB_DIR}" >>/etc/environment
fi

if grep -q "^U2NET_HOME=" /etc/environment 2>/dev/null; then
  sed -i "s#^U2NET_HOME=.*#U2NET_HOME=${U2NET_DIR}#" /etc/environment
else
  printf "U2NET_HOME=%s\n" "${U2NET_DIR}" >>/etc/environment
fi

echo "Shared HF cache configured:"
ls -ld "${BASE_DIR}" "${BASE_DIR}/models" "${HF_HUB_DIR}" "${U2NET_DIR}" "${BASE_DIR}/cache" "${BASE_DIR}/outputs"
getent group "${GROUP_NAME}"
find "${U2NET_DIR}" -maxdepth 1 -type f -printf "%f %s\n" | sort
cat /etc/profile.d/adnova-hf-cache.sh
