
from pathlib import Path


def format_srt_timestamp(seconds: float) -> str:
    """Convert seconds into an SRT timestamp."""
    total_ms = round(seconds * 1000)

    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)

    return (
        f"{hours:02}:{minutes:02}:{secs:02},"
        f"{milliseconds:03}"
    )


def generate_srt(
    segments: list[dict],
    output_path: str,
) -> str:
    """Generate an SRT subtitle file from transcription segments."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    subtitle_number = 1

    with output_file.open("w", encoding="utf-8-sig", newline="\n") as file:
        for segment in segments:
            text = segment["text"].strip()

            if not text:
                continue

            start = float(segment["start"])
            end = float(segment["end"])

            if start < 0 or end <= start:
                raise ValueError(
                    f"Invalid subtitle timestamps: {start} - {end}"
                )

            file.write(f"{subtitle_number}\n")
            file.write(
                f"{format_srt_timestamp(start)} --> "
                f"{format_srt_timestamp(end)}\n"
            )
            file.write(f"{text}\n\n")

            subtitle_number += 1

    return str(output_file)
