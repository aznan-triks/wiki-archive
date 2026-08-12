FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl dos2unix \
    libxml2-dev libxslt1-dev \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    libffi-dev libcairo2 \
    ghostscript \
    fonts-liberation fonts-dejavu \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    wikiteam3 \
    mwparserfromhell \
    weasyprint \
    pikepdf \
    beautifulsoup4 \
    markdownify \
    requests \
    psutil \
    fastapi \
    "uvicorn[standard]"

WORKDIR /app
COPY server.py /app/server.py
COPY scripts/ /scripts/
# Convert Windows -> Unix line endings for all scripts
RUN dos2unix /scripts/*.sh /scripts/*.py && chmod +x /scripts/*.sh /scripts/*.py

ENV SCRIPTS_DIR=/scripts DATA_DIR=/data PYTHONUTF8=1
EXPOSE 8080
# dos2unix at startup to handle Windows line endings on mounted volumes
CMD ["bash", "-c", "dos2unix /scripts/*.sh /scripts/*.py 2>/dev/null; exec python /app/server.py"]
