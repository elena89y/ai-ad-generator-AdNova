FROM python:3.11-slim

WORKDIR /app

# COMPUTE=cpu(기본, v6 T5 생존 이미지): GPU 전용 핀을 빌드 시점에 치환/제거한다.
#   - onnxruntime-gpu: sys_platform=="linux" 마커가 VM(x86+CUDA)용인데 컨테이너도 linux 라 걸림.
#     arm64/CPU 휠이 없어 빌드 실패(실측 2026-07-21) → CPU 런타임으로 치환.
#   - bitsandbytes: NF4(FLUX/Kontext) 전용 — CPU 웹 경로는 임포트하지 않음 → 제외.
#   VM venv 는 원본 requirements.txt 그대로 사용(rembg CPU 우회 금지 규칙 불변).
# GPU 워커 이미지: --build-arg COMPUTE=gpu (compose gpu-worker 프로파일이 지정).
ARG COMPUTE=cpu
COPY requirements.txt .
RUN if [ "$COMPUTE" = "gpu" ]; then \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      sed -e 's/^onnxruntime-gpu.*/onnxruntime/' -e '/^bitsandbytes/d' requirements.txt > /tmp/req.cpu.txt \
      && pip install --no-cache-dir -r /tmp/req.cpu.txt; \
    fi

COPY app ./app
COPY assets ./assets

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
