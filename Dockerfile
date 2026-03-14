FROM python:3.12-slim

# Install system dependencies required by Camoufox/Playwright (Firefox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libnss3 \
    libnspr4 \
    libasound2 \
    fonts-liberation \
    nano \
    fish \
    && rm -rf /var/lib/apt/lists/*

# Set fish as the default shell
RUN chsh -s /usr/bin/fish

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the Camoufox browser binary
RUN python -m camoufox fetch

COPY . .
# copy from / to /app
#COPY . /app

CMD ["python", "main.py"]
#CMD ["sleep", "100"]

