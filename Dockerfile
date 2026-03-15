FROM python:3.11-slim

# Install Chromium, Driver, and Mesa (Required for Software WebGL)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libosmesa6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Render uses port 10000 by default
EXPOSE 10000

CMD ["python", "bot.py"]
