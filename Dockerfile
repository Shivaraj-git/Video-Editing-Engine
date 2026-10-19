FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    HF_HOME=/opt/hf-cache

# FFmpeg + ffprobe (Debian build includes libx264 and libass for subtitles).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the Whisper "base" model into the image so the container starts fast
# and never needs the internet at run time.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
ENV HF_HUB_OFFLINE=1

COPY *.py ./

# Run as a non-root user; uploads/ and outputs/ are writable by it.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/uploads /app/outputs \
    && chown -R appuser:appuser /app /opt/hf-cache
USER appuser

EXPOSE 8000 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
