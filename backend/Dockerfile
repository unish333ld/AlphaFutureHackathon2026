FROM python:3.14-slim@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0=1.56.3-1 libpangoft2-1.0-0=1.56.3-1 \
    libharfbuzz-subset0=10.2.0-1+deb13u1 fonts-dejavu-core=2.37-8 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r /app/requirements.lock \
    && useradd --create-home --uid 10001 credit
COPY --chown=credit:credit backend /app/backend
COPY --chown=credit:credit pyproject.toml /app/pyproject.toml
COPY --chown=credit:credit scripts /app/scripts
COPY --chown=credit:credit docs/openapi.yaml /app/docs/openapi.yaml
WORKDIR /app/backend
USER credit
EXPOSE 8000
CMD ["sh", "/app/backend/entrypoint.sh"]
