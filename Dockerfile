FROM python:3.12-slim

WORKDIR /code

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Pre-download the embedding model so it's cached in the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
