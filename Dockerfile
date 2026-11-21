FROM python:3.15.2-slim-trixie

WORKDIR /app
COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt \
    && useradd --system --no-create-home --uid 10001 app

COPY app.py gunicorn_config.py ./

USER 10001

EXPOSE 8085

CMD ["gunicorn", "--config", "gunicorn_config.py", "app:app"]