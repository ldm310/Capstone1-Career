FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/data-pipeline/external-pass-crawler
WORKDIR /app
COPY data-pipeline/external-pass-crawler/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --uid 10001 --create-home crawler
COPY data-pipeline/external-pass-crawler/external_pass_crawler /app/data-pipeline/external-pass-crawler/external_pass_crawler
COPY db/init/04-external-pass-material.sql /app/db/init/04-external-pass-material.sql
COPY db/migrations/07-external-pass-collection-requests.sql /app/db/migrations/07-external-pass-collection-requests.sql
COPY db/migrations/08-external-pass-daily.sql /app/db/migrations/08-external-pass-daily.sql
USER crawler
ENTRYPOINT ["python", "-m", "external_pass_crawler.comparison_batch"]
CMD ["--help"]
