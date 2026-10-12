FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Pinned closure (requirements*.txt). The project itself is not installed:
# the app runs from /app.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
