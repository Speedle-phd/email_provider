FROM python:3.15.2-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

# Unbuffered logs reach `docker compose logs` immediately; the root filesystem
# is read-only at runtime, so skip writing bytecode caches.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt .

# requirements.txt carries hashes, so pip verifies every package it installs.
RUN pip3 install --no-cache-dir --require-hashes -r requirements.txt \
    && useradd --system --no-create-home --uid 10001 app

COPY app.py gunicorn_config.py ./

USER 10001

EXPOSE 8085

CMD ["gunicorn", "--config", "gunicorn_config.py", "app:app"]
