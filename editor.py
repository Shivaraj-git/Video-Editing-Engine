
import json
import subprocess
from pathlib import Path


def trim_video(
    input_path: str,
    output_path: str,
    start_seconds: float,
    end_seconds: float,
) -> dict:
    """Trim a video between exact start and end timestamps."""

    source = Path(input_path)
    destination = Path(output_path)

    if not source.is_file():
        raise FileNotFoundError(f"Input video not found: {source}")

    if start_seconds < 0:
        raise ValueError("Start time cannot be negative.")

    if end_seconds <= start_seconds:
        raise ValueError("End time must be greater than start time.")

    destination.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-i", str(source),
        "-ss", str(start_seconds),
        "-t", str(end_seconds - start_seconds),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(destination),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Video rendering timed out.") from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg rendering failed:\n{result.stderr[-3000:]}"
        )

    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("FFmpeg did not produce a valid output file.")

    return {
        "input": str(source),
        "output": str(destination),
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "duration_seconds": end_seconds - start_seconds,
        "output_size_bytes": destination.stat().st_size,
        "status": "completed",
    }

def remove_section(input_path, output_path, remove_start, remove_end):
    """Remove a time range and join the remaining video and audio."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")

    if remove_start < 0 or remove_end <= remove_start:
        raise ValueError("Invalid removal time range.")

    # Read video duration and check whether audio exists.
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type",
            "-of", "json", str(input_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    info = json.loads(probe.stdout)
    duration = float(info["format"]["duration"])
    has_audio = any(
        stream.get("codec_type") == "audio"
        for stream in info.get("streams", [])
    )

    if remove_end >= duration:
        raise ValueError(
            f"Removal end time must be less than video duration ({duration:.2f}s)."
        )

    # Keep the part before the removed section and the part after it.
    filters = [
        f"[0:v:0]trim=start=0:end={remove_start},"
        "setpts=PTS-STARTPTS[v0]",
        f"[0:v:0]trim=start={remove_end}:end={duration},"
        "setpts=PTS-STARTPTS[v1]",
        "[v0][v1]concat=n=2:v=1:a=0[vout]",
    ]

    command = ["ffmpeg", "-y", "-i", str(input_path)]

    if has_audio:
        filters.extend([
            f"[0:a:0]atrim=start=0:end={remove_start},"
            "asetpts=PTS-STARTPTS[a0]",
            f"[0:a:0]atrim=start={remove_end}:end={duration},"
            "asetpts=PTS-STARTPTS[a1]",
            "[a0][a1]concat=n=2:v=0:a=1[aout]",
        ])

    command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])

    if has_audio:
        command.extend(["-map", "[aout]"])

    command.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
    ])

    if has_audio:
        command.extend(["-c:a", "aac"])

    command.extend([
        "-movflags", "+faststart",
        str(output_path),
    ])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=600,
    )

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-2000:]}")

    return {
        "input": str(input_path),
        "output": str(output_path),
        "removed_start_seconds": remove_start,
        "removed_end_seconds": remove_end,
        "duration_seconds": round(duration - (remove_end - remove_start), 3),
        "status": "completed",
    }

def burn_subtitles(
    video_path: str,
    subtitle_path: str,
    output_path: str,
) -> str:
    """Burn SRT subtitles permanently into a video."""
    video = Path(video_path).resolve()
    subtitles = Path(subtitle_path).resolve()
    output = Path(output_path).resolve()

    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")

    if not subtitles.is_file():
        raise FileNotFoundError(
            f"Subtitle file not found: {subtitles}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    # Escape the path for FFmpeg's subtitles filter on Windows.
    subtitle_filter_path = (
        str(subtitles)
        .replace("\\", "/")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )

    command = [
        "ffmpeg",
        "-y",
        "-i", str(video),
        "-vf",
        f"subtitles=filename='{subtitle_filter_path}'",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        str(output),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg subtitle burning failed:\n{result.stderr}"
        )

    return str(output)
