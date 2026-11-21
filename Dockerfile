FROM python:3.15.2-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

WORKDIR /app
COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt \
    && useradd --system --no-create-home --uid 10001 app

COPY app.py gunicorn_config.py ./

USER 10001

EXPOSE 8085

CMD ["gunicorn", "--config", "gunicorn_config.py", "app:app"]