FROM python:3.11-slim

RUN groupadd -g 1000 anthem && useradd -u 1000 -g anthem -m anthem
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY anthem-common/ /app/anthem-common/
RUN pip install --no-cache-dir /app/anthem-common/ pyyaml httpx uvicorn[standard]

COPY cortex-gateway/ /app/cortex-gateway/
ENV PYTHONPATH=/app:/app/cortex-gateway

USER anthem
EXPOSE 8080
CMD ["uvicorn", "gateway.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
