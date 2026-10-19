# AI tool use

> Edit this so it matches what you actually did.

| Tool | Used for |
|---|---|
| ChatGPT (OpenAI) | Initial project: FastAPI endpoints, FFmpeg trim / remove-section / subtitle-burn functions, faster-whisper transcription, SRT generator, regex instruction parser, first Gradio UI. |
| Claude (Anthropic) | The "one instruction at a time" guard (`ensure_single_instruction` in `instruction_parser.py` and the hint text in the UI); the undo / redo / revert version history in `app.py` and moving it into the layout; code review and timing tests of the project (which found the `remove_section` memory problem described in `REPORT.md`); this README, REPORT, SOURCES and AI_USE. |

## AI models inside the product

* Whisper `base` via faster-whisper, running locally, used only for
  subtitles.
* No hosted AI service or API key is used.

## How AI output was checked

AI-written code was run by hand on sample clips. The timings in `REPORT.md`
were measured on a synthetic clip, not estimated. This version has no
automated test suite.
