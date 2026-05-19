FROM python:3.11-slim

RUN groupadd -g 1000 anthem && useradd -u 1000 -g anthem -m anthem
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY anthem-common/ /app/anthem-common/
RUN pip install --no-cache-dir /app/anthem-common/ numpy pyyaml uvicorn[standard]

COPY bue/ /app/bue/
COPY configs/ /app/configs/
ENV PYTHONPATH=/app

USER anthem
EXPOSE 9000
CMD ["uvicorn", "bue.api:app", "--host", "0.0.0.0", "--port", "9000"]
