FROM python:3.11-slim

# Install system dependencies for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libasound2 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Expose port (Koyeb default port is 8000)
EXPOSE 8000
ENV PORT=8000 PYTHONUNBUFFERED=1

# Run the assistant application
CMD ["python", "main.py"]
