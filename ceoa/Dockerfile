FROM python:3.12-slim

RUN groupadd -r anthem && useradd -r -g anthem -u 1000 anthem

WORKDIR /app
COPY anthem-common/ ./anthem-common/
RUN pip install -e ./anthem-common/
COPY ceoa/ ./ceoa/
RUN pip install fastapi uvicorn httpx pyyaml

USER anthem
EXPOSE 7100

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:7100/health || exit 1

CMD ["uvicorn", "ceoa.api:app", "--host", "0.0.0.0", "--port", "7100"]
