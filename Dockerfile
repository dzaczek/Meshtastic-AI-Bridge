FROM python:3.11-slim

# System dependencies (build tools + curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright / Chromium - only needed if AI web scraping is used (weather, search).
# Uncomment the line below to enable - adds ~500MB to image.
# RUN playwright install chromium --with-deps

# Copy application code
COPY . .

# Ensure config.py exists
RUN if [ ! -f config.py ]; then cp config_template.py config.py; fi

# Create directories for persistent data
RUN mkdir -p conversations .map_cache logs

# Web UI port
EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

CMD ["python", "main_app.py", "--headless"]
