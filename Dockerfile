FROM python:3.12-slim

WORKDIR /code

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

# Download embedding model at startup only if not already cached (volume-backed)
ENV HF_HOME=/root/.cache/huggingface

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
