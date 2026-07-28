FROM python:3.11-slim

WORKDIR /app

# COMPUTE=cpu(기본)는 8100 생성 서버를 호출하는 웹 API 이미지다.
# 모델 의존성은 requirements.txt에 남기고, 웹 이미지는 requirements.web.txt만 설치한다.
# GPU 워커 이미지는 --build-arg COMPUTE=gpu로 기존 전체 의존성을 설치한다.
ARG COMPUTE=cpu
COPY requirements.txt requirements.web.txt ./
RUN if [ "$COMPUTE" = "gpu" ]; then \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.web.txt; \
    fi

COPY app ./app
COPY assets ./assets

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
