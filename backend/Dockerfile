FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
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
