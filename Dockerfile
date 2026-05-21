FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -y && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        musl-dev \
        ffmpeg \
        make \
        g++ \
        wget \
        unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

CMD ["sh", "-c", "cd modules && gunicorn --bind 0.0.0.0:${PORT:-8000} main:flask_app --workers 1 & python3 main.py"]
