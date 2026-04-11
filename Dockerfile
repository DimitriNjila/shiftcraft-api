FROM python:3.11-slim

WORKDIR /app


RUN pip install uv

RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync 

COPY . .

EXPOSE 8000


CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]