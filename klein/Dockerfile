FROM python:3.12-slim

RUN groupadd -r anthem && useradd -r -g anthem -u 1000 anthem

WORKDIR /app
COPY anthem-common/ ./anthem-common/
RUN pip install -e ./anthem-common/
COPY klein/ ./klein/
RUN pip install fastapi uvicorn httpx pyyaml pydantic

USER anthem
EXPOSE 7200

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:7200/health || exit 1

CMD ["uvicorn", "klein.api:app", "--host", "0.0.0.0", "--port", "7200"]
