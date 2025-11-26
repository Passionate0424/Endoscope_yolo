#!/bin/bash
# Bootstrap a C-only K230 firmware workspace inside WSL
# - Assumes repo cloned at /mnt/e/project/Endoscope_yolo
# - Uses existing clean SDK at ~/canmv_k230_clean (if not present, you must repo init/sync manually)
# - Creates a working copy at ~/canmv_k230_c_firmware and syncs sources/model

set -euo pipefail

PROJECT_DIR="/mnt/e/project/Endoscope_yolo"
SDK_BASE="${HOME}/canmv_k230_clean"
SDK_WORK="${HOME}/canmv_k230_c_firmware"

echo "[INFO] Project dir: ${PROJECT_DIR}"
echo "[INFO] Clean SDK:   ${SDK_BASE}"
echo "[INFO] Work SDK:    ${SDK_WORK}"

if [ ! -d "${SDK_BASE}" ]; then
  echo "[WARN] ${SDK_BASE} not found. Please run repo init/sync per docs/SDK_INTEGRATION_MODIFICATIONS.md first."
  exit 1
fi

if [ -d "${SDK_WORK}" ]; then
  echo "[INFO] Reusing existing ${SDK_WORK}"
else
  echo "[INFO] Copying clean SDK to work dir..."
  cp -a "${SDK_BASE}" "${SDK_WORK}"
fi

pushd "${SDK_WORK}" >/dev/null

# sync HTTP/Yolo app sources
APP_DST="src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server"
echo "[INFO] Syncing rtsmart_userapp -> ${APP_DST}"
rsync -a --delete "${PROJECT_DIR}/rtsmart_userapp/" "${APP_DST}/"

# copy YOLO reference sources
YOLO_SRC="${PROJECT_DIR}/k230_yolo_ref/YOLO/src"
YOLO_DST="${APP_DST}/yolo_ref"
if [ -d "${YOLO_SRC}" ]; then
  echo "[INFO] Syncing YOLO reference sources"
  mkdir -p "${YOLO_DST}"
  rsync -a --delete "${YOLO_SRC}/" "${YOLO_DST}/"
else
  echo "[WARN] YOLO reference src not found at ${YOLO_SRC}; skip."
fi

# copy kmodel and labels if present
MODEL_SRC="${PROJECT_DIR}/build/k230_pytorch_env/model.kmodel"
LABEL_SRC="${PROJECT_DIR}/build/k230_pytorch_env/labels.txt"
DATA_DST="${APP_DST}/data"
mkdir -p "${DATA_DST}"
if [ -f "${MODEL_SRC}" ]; then
  echo "[INFO] Copying model.kmodel"
  cp "${MODEL_SRC}" "${DATA_DST}/model.kmodel"
else
  echo "[WARN] model.kmodel not found at ${MODEL_SRC}"
fi
if [ -f "${LABEL_SRC}" ]; then
  echo "[INFO] Copying labels.txt"
  cp "${LABEL_SRC}" "${DATA_DST}/labels.txt"
else
  echo "[WARN] labels.txt not found at ${LABEL_SRC}"
fi

echo "[INFO] Ready to build. Suggested commands:"
echo "  cd ${SDK_WORK}"
echo "  make k230_canmv_lckfb_defconfig"
echo "  make clean && make -j\$(nproc)"
echo ""
echo "[INFO] Firmware output: ${SDK_WORK}/output/k230_canmv_lckfb_defconfig/"

popd >/dev/null
