FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/bot.db \
    MPLCONFIGDIR=/tmp/matplotlib

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

CMD ["python", "-m", "bot.main"]
