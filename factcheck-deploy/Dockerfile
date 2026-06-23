FROM python:3.11-slim

# ffmpeg requis par faster-whisper (normalisation audio) et yt-dlp (extraction audio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend

# Hugging Face Spaces (Docker) route le trafic public vers le port 7860
ENV PORT=7860
EXPOSE 7860

WORKDIR /app/backend
CMD ["python", "main.py"]
