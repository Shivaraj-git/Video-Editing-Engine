from editor import trim_video, remove_section
import json
import subprocess
from fastapi import HTTPException
from transcriber import transcribe_video
from subtitle_generator import generate_srt
from editor import burn_subtitles
from uuid import UUID
from pathlib import Path
from uuid import uuid4
from fastapi.responses import FileResponse
from pydantic import BaseModel
from instruction_parser import parse_instruction
from fastapi import FastAPI, File, HTTPException, UploadFile

class InstructionEditRequest(BaseModel):
    video_id: str
    instruction: str

app = FastAPI(
    title="Natural Language Video Editing Engine",
    version="0.1.0",
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


@app.get("/")
def home():
    return {"message": "Video Editing Engine is running!"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file extension. Use MP4, MOV, MKV, or WEBM.",
        )

    video_id = str(uuid4())
    destination = UPLOAD_DIR / f"{video_id}{extension}"
    size = 0

    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)

                if size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Video exceeds the 500 MB upload limit.",
                    )

                output.write(chunk)

        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        return {
            "video_id": video_id,
            "filename": original_name,
            "size_bytes": size,
            "status": "uploaded",
        }

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        await file.close()

@app.get("/videos/{video_id}/metadata")
def get_video_metadata(video_id: str):
    try:
        video_id = str(UUID(video_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid video ID")

    matches = list(UPLOAD_DIR.glob(f"{video_id}.*"))

    if not matches:
        raise HTTPException(status_code=404, detail="Video not found")

    video_path = matches[0]

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height,avg_frame_rate",
                "-of", "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        data = json.loads(result.stdout)
        streams = data.get("streams", [])

        video_stream = next(
            (s for s in streams if s.get("codec_type") == "video"),
            {},
        )

        audio_stream = next(
            (s for s in streams if s.get("codec_type") == "audio"),
            None,
        )

        return {
            "video_id": video_id,
            "duration_seconds": float(
                data.get("format", {}).get("duration", 0)
            ),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "frame_rate": video_stream.get("avg_frame_rate"),
            "has_audio": audio_stream is not None,
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504, detail="Video analysis timed out"
        )
    except (subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=422, detail="Could not read video metadata"
        )


from pydantic import BaseModel


class TrimRequest(BaseModel):
    video_id: UUID
    start_seconds: float
    end_seconds: float


@app.post("/trim")
def trim_endpoint(request: TrimRequest):
    video_id = str(request.video_id)

    matches = list(UPLOAD_DIR.glob(f"{video_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Uploaded video not found")

    if request.start_seconds < 0:
        raise HTTPException(
            status_code=400,
            detail="Start time cannot be negative",
        )

    if request.end_seconds <= request.start_seconds:
        raise HTTPException(
            status_code=400,
            detail="End time must be greater than start time",
        )

    output_path = OUTPUT_DIR / f"{video_id}_trim.mp4"

    try:
        result = trim_video(
            input_path=str(matches[0]),
            output_path=str(output_path),
            start_seconds=request.start_seconds,
            end_seconds=request.end_seconds,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "message": "Video trimmed successfully",
        **result,
        "download_url": f"/outputs/{output_path.name}",
    }

@app.get(
    "/outputs/{filename}",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "video/mp4": {},
                "application/x-subrip": {},
            },
            "description": "Rendered video or subtitle file",
        }
    },
)
def download_output(filename: str):
    allowed_suffixes = (
        "_trim.mp4",
        "_instruction_trim.mp4",
        "_section_removed.mp4",
        "_subtitled.mp4",
        "_subtitles.srt",
    )

    if (
        Path(filename).name != filename
        or not filename.endswith(allowed_suffixes)
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename.",
        )

    output_path = OUTPUT_DIR / filename

    if not output_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Output file not found.",
        )

    if filename.endswith(".srt"):
        media_type = "application/x-subrip"
    else:
        media_type = "video/mp4"

    return FileResponse(
        path=output_path,
        media_type=media_type,
        filename=filename,
    )

@app.post("/edit-by-instruction")
def edit_by_instruction(request: InstructionEditRequest):
    # Validate the video ID.
    try:
        video_id = str(UUID(request.video_id))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid video ID.",
        )

    # Find the uploaded video.
    input_files = list(UPLOAD_DIR.glob(f"{video_id}.*"))

    if not input_files or not input_files[0].is_file():
        raise HTTPException(
            status_code=404,
            detail="Video not found.",
        )

    input_path = input_files[0]

    # Parse the user's instruction.
    try:
        edit_plan = parse_instruction(request.instruction)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    operation = edit_plan["operation"]

    # Handle subtitle instructions separately.
    # Subtitle plans do not contain start_seconds or end_seconds.
    if operation == "add_subtitles":
        subtitle_path = OUTPUT_DIR / f"{video_id}_subtitles.srt"
        output_path = OUTPUT_DIR / f"{video_id}_subtitled.mp4"

        try:
            segments = transcribe_video(str(input_path))

            if not segments:
                raise HTTPException(
                    status_code=422,
                    detail="No speech detected in the video.",
                )

            generate_srt(
                segments,
                str(subtitle_path),
            )

            burn_subtitles(
                str(input_path),
                str(subtitle_path),
                str(output_path),
            )

        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Subtitle generation failed: {error}",
            ) from error

        return {
            "message": "Subtitles generated successfully.",
            "edit_plan": edit_plan,
            "subtitle_segments": len(segments),
            "subtitle_file": f"/outputs/{subtitle_path.name}",
            "download_url": f"/outputs/{output_path.name}",
        }

    # The remaining operations require timestamps.
    if operation not in {"trim", "remove_section"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported editing operation.",
        )

    start = edit_plan["start_seconds"]
    end = edit_plan["end_seconds"]

    if start < 0 or end <= start:
        raise HTTPException(
            status_code=400,
            detail="Invalid editing time range.",
        )

    # Read the actual video duration.
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(input_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        duration = float(
            json.loads(result.stdout)["format"]["duration"]
        )

    except (
        subprocess.SubprocessError,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        raise HTTPException(
            status_code=500,
            detail="Could not read video duration.",
        ) from error

    if end > duration:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requested times must be within the video "
                f"duration ({duration:.2f} seconds)."
            ),
        )

    # Render the requested edit.
    if operation == "trim":
        output_filename = f"{video_id}_instruction_trim.mp4"
        output_path = OUTPUT_DIR / output_filename

        try:
            render_result = trim_video(
                str(input_path),
                str(output_path),
                start,
                end,
            )

        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Video trimming failed: {error}",
            ) from error

    else:
        output_filename = f"{video_id}_section_removed.mp4"
        output_path = OUTPUT_DIR / output_filename

        try:
            render_result = remove_section(
                str(input_path),
                str(output_path),
                start,
                end,
            )

        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Section removal failed: {error}",
            ) from error

    return {
        "message": "Instruction processed successfully.",
        "edit_plan": edit_plan,
        "render_result": render_result,
        "download_url": f"/outputs/{output_filename}",
    }


@app.post("/videos/{video_id}/subtitles")
def create_subtitled_video(video_id: str):
    # Validate the video ID.
    try:
        UUID(video_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid video ID.",
        )

    uploads_dir = Path("uploads")
    outputs_dir = Path("outputs")

    # Find the uploaded video regardless of its extension.
    matches = list(uploads_dir.glob(f"{video_id}.*"))

    if not matches or not matches[0].is_file():
        raise HTTPException(
            status_code=404,
            detail="Uploaded video not found.",
        )

    video_path = matches[0]
    subtitle_path = outputs_dir / f"{video_id}_subtitles.srt"
    output_path = outputs_dir / f"{video_id}_subtitled.mp4"

    try:
        # 1. Transcribe speech.
        segments = transcribe_video(str(video_path))

        if not segments:
            raise HTTPException(
                status_code=422,
                detail="No speech detected in the video.",
            )

        # 2. Generate SRT subtitles.
        generate_srt(segments, str(subtitle_path))

        # 3. Burn subtitles into the video.
        burn_subtitles(
            str(video_path),
            str(subtitle_path),
            str(output_path),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Subtitle generation failed: {exc}",
        ) from exc

    return {
        "status": "success",
        "video_id": video_id,
        "subtitle_segments": len(segments),
        "subtitle_file": f"/outputs/{subtitle_path.name}",
        "download_url": f"/outputs/{output_path.name}",
    }
