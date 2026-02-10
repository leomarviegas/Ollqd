FROM python:3.12-slim

WORKDIR /app

# Install only what's needed
COPY pyproject.toml .
COPY src/ src/
COPY codebase_indexer.py codebase_search.py ./

RUN pip install --no-cache-dir ".[web]"
RUN python -m spacy download en_core_web_sm

# Docling (opt-in via build arg, uses CPU-only PyTorch)
ARG INSTALL_DOCLING=true
RUN if [ "$INSTALL_DOCLING" = "true" ]; then \
      pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        "docling>=2.0"; \
      python -c "from docling.document_converter import DocumentConverter; print('Docling OK')"; \
    fi

RUN mkdir -p /uploads

EXPOSE 8000

CMD ["ollqd-web"]
