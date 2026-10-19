from faster_whisper import WhisperModel

# Load the Base model once and reuse it.
model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8",
)


def transcribe_video(video_path: str) -> list[dict]:
    """Return speech segments with start/end timestamps and text."""

    segments, info = model.transcribe(
        str(video_path),
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=True,
    )

    results = []

    for segment in segments:
        results.append({
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "text": segment.text.strip(),
        })

    return results
