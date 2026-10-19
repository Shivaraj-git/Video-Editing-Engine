# Sources

Nothing in this version calls a paid or hosted AI service. All AI runs
locally.

## Models

| Item | Used for | Licence |
|---|---|---|
| OpenAI Whisper `base` weights (CTranslate2 conversion `Systran/faster-whisper-base` from Hugging Face, downloaded by faster-whisper at first start) | speech-to-text for subtitles | MIT (per model card; re-check before release) |

## Libraries and tools

| Item | Used for | Licence |
|---|---|---|
| faster-whisper | runs Whisper | MIT |
| CTranslate2 (dependency of faster-whisper) | inference engine | MIT |
| FastAPI / Starlette | HTTP API | MIT / BSD-3 |
| Uvicorn | ASGI server | BSD-3 |
| Pydantic | request models | MIT |
| python-multipart | file uploads | Apache-2.0 |
| requests | UI-to-API calls | Apache-2.0 |
| Gradio | web UI | Apache-2.0 |
| FFmpeg / ffprobe (with libass) | trimming, joining, subtitle burn-in | LGPL-2.1+ or GPL-2+ depending on build |
| x264 (libx264, inside FFmpeg) | H.264 encoding | GPL-2.0+ |

**FFmpeg / x264 note.** The code runs the `ffmpeg` binary as a separate
process; it is not linked into the project. Using it inside a hosted service
is generally fine. If IncuBrix **distributes** an FFmpeg build containing
libx264 (GPL), GPL obligations or a commercial x264 licence apply. Options:
ship an LGPL-only FFmpeg build with a different H.264 encoder, or buy the
x264 commercial licence. Get a legal review before shipping binaries.

## Datasets and media

None are included. Timing tests used a synthetic clip generated with
FFmpeg's `testsrc` and `sine` sources. **Do not put third-party footage
(for example film or TV clips) in the repository or demo**: it is not
cleared for commercial use. Subtitles are rendered with whatever font the
host provides; choose a commercially licensed font when shipping.

## Code

All project code was written for this project with the AI assistance listed
in `AI_USE.md`. No code was copied from AGPL projects. No API keys or secrets
exist in the code.
