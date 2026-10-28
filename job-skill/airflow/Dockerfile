# syntax=docker/dockerfile:1
# Airflow 3.3.2 + 우리 파이프라인 패키지. 빌드 전에 GPU 휠을 airflow/wheels/ 에 받아 둔다(README "Airflow로 돌리기").
FROM apache/airflow:3.3.2-python3.12

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# OCR 전용 가상환경: paddlex 는 PyYAML==6.0.2 를 고정하고 Airflow 는 pyyaml>=6.0.3 이 필요해 한 환경에 둘 수 없다.
# GPU 휠(1.9GB)은 빌드 중에만 붙여 쓰고(이미지에 사본을 남기지 않음), 나머지 의존성(CUDA 라이브러리 등)은 PyPI 에서 받는다.
# pip 캐시는 빌드 캐시에만 둔다 — 빌드가 중간에 실패해도 다시 할 때 이미 받은 파일을 또 받지 않게.
RUN --mount=type=bind,source=wheels,target=/wheels \
    --mount=type=cache,target=/root/.cache/pip \
    python -m venv /opt/paddle \
 && /opt/paddle/bin/pip install --timeout 120 --retries 10 \
      /wheels/paddlepaddle_gpu-3.2.2-cp312-cp312-linux_x86_64.whl "paddleocr==3.7.0"

USER airflow
COPY requirements-airflow.txt /tmp/requirements-airflow.txt
RUN --mount=type=cache,target=/home/airflow/.cache/pip,uid=50000 \
    pip install "apache-airflow==3.3.2" -r /tmp/requirements-airflow.txt
