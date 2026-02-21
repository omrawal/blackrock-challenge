# Build: docker build -t blk-hacking-ind-{name-lastname} .
# Run:   docker run -d -p 5477:5477 blk-hacking-ind-{name-lastname}

# Using python:3.12-slim (Debian Bookworm):
#   - Minimal attack surface vs full python image (~50 MB vs 1 GB)
#   - Official Python slim images receive regular security patches
#   - Debian LTS ensures long-term library compatibility
#   - No unnecessary OS tools that could be exploited
FROM python:3.12-slim

LABEL maintainer="challenger"
LABEL version="1.0.0"
LABEL description="BlackRock Retirement Savings API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

# Non-root user for security best practice
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir flask psutil

COPY main.py business.py ./

RUN chown -R appuser:appuser /app

USER appuser

# Expose the required port
EXPOSE 5477

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5477/health')"

CMD ["python", "main.py"]
