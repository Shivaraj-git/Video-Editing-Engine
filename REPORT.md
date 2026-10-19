# Report: Prompt-Based Video Editing Engine

## 1. What it does

A user uploads a video and writes one plain-English instruction. The system
trims it, removes a section, or adds burned-in subtitles, and keeps every
result as a version that can be reverted.

## 2. Approaches considered

**Understanding the instruction**

| Option | Pros | Cons | Chosen? |
|---|---|---|---|
| Regex rules | free, instant, deterministic, easy to reason about, no data leaves the machine | narrow phrasing | **Yes** |
| LLM turns the sentence into a JSON plan | handles free phrasing | paid, slower, depends on a provider, output must be validated | No |
| LLM writes FFmpeg commands | most flexible | model output would be executed: unsafe | No |

Rules were enough for three operations and keep the default path free and
offline. Because the rules only read the first matching pattern, a message
with two edits used to be half-ignored silently; a guard now rejects those
and asks for one instruction at a time.

**Speech-to-text.** Local `faster-whisper` with the `base` model (MIT
licence): no per-minute cost, no audio leaves the machine, runs on CPU.
Hosted ASR APIs are more accurate but cost money and need keys.

**Revertible changes.** Instead of one mutable output, every edit creates a
new file/version. Undo and redo then just change which version is shown, so
they are instant and cannot corrupt anything.

**Architecture.** Gradio UI, FastAPI backend, FFmpeg for all video work.
FFmpeg is the right tool: fast, frame-accurate, and already handles every
container.

## 3. What works

* Trim, remove section, remove first N seconds and subtitles run end to end,
  through both the UI and the API.
* Input checks: file type, 500 MB limit, UUID ids, time-range validation
  against the real duration, safe download filenames.
* Multi-instruction messages are rejected with a clear message and the text
  stays in the box.
* Undo, redo and jump-to-version in the UI; editing from an older version
  drops the old redo branch.
* On short clips (tested on 10 s) `remove_section` gives correct lengths for
  a middle cut and for "remove the first 2 seconds".

## 4. What does not work, and why

1. **`remove_section` runs out of memory on longer videos.** It splits one
   decoded stream into two `trim` branches, and FFmpeg buffers raw frames
   while it waits. On a 2-minute 720p clip it was killed (consistent with
   exhausting the 4 GB of the test machine). Fix: read the two kept parts as
   two separately seeked inputs and join them with `concat`.
2. **Removing up to the very end gives HTTP 500, not 400.** `main.py`
   accepts `end == duration`, but `remove_section` requires `end <
   duration`; the resulting error is reported as a server error.
3. **Narrow grammar.** Seconds only. No `mm:ss`, no "last 5 seconds", no
   minutes.
4. **Every edit is a full re-encode** (CRF 18). It is slow and each
   generation loses a little quality.
5. **Versions are stored by re-uploading each result.** Disk use grows with
   every edit; nothing is cleaned up. History is lost on page refresh.
6. **Subtitles:** one fixed style, segment-level timing, system fonts;
   accuracy of `base` drops on names, jargon and noisy audio. The Whisper
   model loads at server start, so importing `main.py` always needs the
   model.
7. **Operations:** FFmpeg runs inside the request (no queue, no progress),
   no authentication or rate limits, uploads are checked by extension only,
   subtitle burning has no timeout.
8. **No automated tests, no batch runner, no config via environment, no
   per-request cost report, and AI components are not behind swappable
   adapters with a mock.** These are gaps against the IncuBrix rules.

## 5. What I would do next

1. Fix `remove_section` (two seeked inputs + `concat`) and the 500-vs-400
   error; add regression tests.
2. Add a test suite and a mock transcriber so tests need no model or keys.
3. Put transcription and instruction parsing behind small adapters chosen by
   environment variables, with an optional LLM parser whose output is
   schema-validated.
4. Return time and cost per video minute from every request and add a batch
   runner.
5. Measure Whisper speed and word error rate on cleared audio; choose the
   model size by cost and accuracy.
6. Job queue with progress, authentication, timeouts, cleanup of old
   versions; store the original plus a recipe of edits instead of a
   re-encoded file per version.
7. Resolve the FFmpeg/x264 licensing route before distributing binaries.
