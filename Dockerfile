FROM python:3.12-slim

WORKDIR /app

# Install only what's needed
COPY pyproject.toml .
COPY src/ src/
COPY codebase_indexer.py codebase_search.py ./

RUN pip install --no-cache-dir ".[web]"
RUN python -m spacy download en_core_web_sm

RUN mkdir -p /uploads

EXPOSE 8000

CMD ["ollqd-web"]
