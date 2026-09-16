FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY run.py .

RUN useradd --create-home uno && mkdir -p /app/instance && chown -R uno /app
USER uno

EXPOSE 8000
# One worker: rooms live in this process's memory. Threads carry the sockets.
CMD ["gunicorn", "--worker-class", "gthread", "--workers", "1", "--threads", "64", \
     "--bind", "0.0.0.0:8000", "--access-logfile", "-", "run:app"]
