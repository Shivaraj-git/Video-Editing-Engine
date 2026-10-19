import os
import tempfile
from pathlib import Path

import gradio as gr
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

EXAMPLES = [
    "Trim the video from 5 seconds to 15 seconds",
    "Remove the first 2 seconds",
    "Remove from 10 seconds to 12 seconds",
    "Add subtitles to the video",
]


# ---------------------------------------------------------------------------
# Backend helpers
# ---------------------------------------------------------------------------

def _post_upload(video_path):
    """Upload a local file to the API and return the response JSON."""
    video_path = Path(video_path)

    with video_path.open("rb") as video_file:
        response = requests.post(
            f"{API_BASE_URL}/upload",
            files={"file": (video_path.name, video_file)},
            timeout=120,
        )

    response.raise_for_status()
    data = response.json()

    if not data.get("video_id"):
        raise ValueError(f"Upload response missing video_id: {data}")

    return data


def _download_output(download_url):
    """Download a rendered file from the API into a temp file."""
    with requests.get(
        f"{API_BASE_URL}{download_url}",
        stream=True,
        timeout=3600,
    ) as file_response:
        file_response.raise_for_status()

        suffix = Path(download_url).suffix or ".mp4"

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        ) as output_file:
            for chunk in file_response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output_file.write(chunk)

            return output_file.name


# ---------------------------------------------------------------------------
# Version history helpers
#
# history: list of {"label": str, "video_id": str, "path": str}
# index:   position of the version currently shown (the "current" version)
#
# Every successful edit is stored as a NEW version (re-uploaded so the
# backend can edit it next). Undo / redo / revert only move `index`, so
# nothing is ever overwritten and no re-rendering is needed.
# ---------------------------------------------------------------------------

def _short(text, limit=60):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _render(history, index, message):
    """Build the full set of UI updates from the current history state."""
    if not history:
        return (
            [],
            0,
            None,
            None,
            message,
            "_No versions yet. Upload a video to begin._",
            gr.update(choices=[], value=None),
            gr.update(interactive=False),
            gr.update(interactive=False),
        )

    current_path = history[index]["path"]

    lines = []
    for i, item in enumerate(history):
        marker = "▶️ **(current)**" if i == index else "&nbsp;&nbsp;&nbsp;"
        lines.append(f"{marker} `{i}` {item['label']}")

    choices = [(f"{i}. {item['label']}", i) for i, item in enumerate(history)]

    return (
        history,
        index,
        current_path,
        current_path,
        message,
        "\n\n".join(lines),
        gr.update(choices=choices, value=index),
        gr.update(interactive=index > 0),
        gr.update(interactive=index < len(history) - 1),
    )


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def upload_video(video_path):
    if not video_path:
        return _render([], 0, "Please select a video first.")

    try:
        data = _post_upload(video_path)
    except requests.RequestException as exc:
        return _render([], 0, f"Upload failed: {exc}")
    except (OSError, ValueError) as exc:
        return _render([], 0, f"Could not upload the selected video: {exc}")

    history = [
        {
            "label": "Original upload",
            "video_id": data["video_id"],
            "path": str(video_path),
        }
    ]

    message = (
        f"Upload successful!\n"
        f"Filename: {data.get('filename', Path(video_path).name)}\n"
        f"Size: {data.get('size_bytes', 0):,} bytes\n"
        f"Tip: give one instruction at a time. You can undo any change."
    )
    return _render(history, 0, message)


def edit_video(history, index, instruction):
    """Apply ONE instruction to the current version and save a new version."""
    if not history:
        return (*_render([], 0, "Please upload your video first."), instruction)

    if not instruction or not instruction.strip():
        return (
            *_render(history, index, "Please enter an editing instruction."),
            instruction,
        )

    current = history[index]

    try:
        response = requests.post(
            f"{API_BASE_URL}/edit-by-instruction",
            json={
                "video_id": current["video_id"],
                "instruction": instruction.strip(),
            },
            timeout=3600,
        )

        try:
            data = response.json()
        except ValueError:
            data = {}

        if not response.ok:
            message = data.get(
                "detail",
                f"Editing failed with HTTP {response.status_code}.",
            )
            # Keep the text so the user can fix it (e.g. split it up).
            return (*_render(history, index, str(message)), instruction)

        download_url = data.get("download_url")

        if not download_url:
            return (
                *_render(history, index, f"No download URL returned: {data}"),
                instruction,
            )

        rendered_path = _download_output(download_url)

        # Register the result as a new video so the next edit builds on it.
        new_upload = _post_upload(rendered_path)

    except requests.RequestException as exc:
        return (*_render(history, index, f"Request failed: {exc}"), instruction)
    except (OSError, ValueError) as exc:
        return (
            *_render(history, index, f"File handling failed: {exc}"),
            instruction,
        )

    # Editing from an older version discards the old "redo" branch.
    new_history = history[: index + 1] + [
        {
            "label": _short(instruction),
            "video_id": new_upload["video_id"],
            "path": rendered_path,
        }
    ]
    new_index = len(new_history) - 1

    message = data.get("message", "Editing completed successfully.")
    message += "\nYou can undo this change with the Undo button."

    return (*_render(new_history, new_index, message), "")


def undo(history, index):
    if not history or index <= 0:
        return _render(history, index, "Nothing to undo.")

    undone = history[index]["label"]
    return _render(history, index - 1, f"Undid: {undone}")


def redo(history, index):
    if not history or index >= len(history) - 1:
        return _render(history, index, "Nothing to redo.")

    redone = history[index + 1]["label"]
    return _render(history, index + 1, f"Redid: {redone}")


def revert_to(history, index, target):
    if not history or target is None:
        return _render(history, index, "Pick a version to revert to.")

    target = int(target)

    if not 0 <= target < len(history):
        return _render(history, index, "That version does not exist.")

    return _render(
        history,
        target,
        f"Reverted to version {target}: {history[target]['label']}",
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Prompt Based Video Editor") as demo:
    gr.Markdown("# Prompt Based Video Editing Engine")
    gr.Markdown(
        "Upload a video, describe your edit, and preview the result."
    )

    history_state = gr.State(value=[])
    index_state = gr.State(value=0)

    with gr.Row():
        with gr.Column():
            input_video = gr.Video(
                label="Original Video",
                sources=["upload"],
            )

            upload_button = gr.Button(
                "Upload Video",
                variant="secondary",
            )

        with gr.Column():
            gr.Markdown(
                "💡 **Give one instruction at a time** for best results. "
                "Each edit builds on the current version, and every change "
                "can be undone."
            )

            instruction = gr.Textbox(
                label="Editing Instruction (one at a time)",
                placeholder="e.g. Trim the video from 5 seconds to 15 seconds",
                lines=2,
                info="One edit per message. Send the next one after this finishes.",
            )

            gr.Examples(examples=EXAMPLES, inputs=instruction)

            edit_button = gr.Button(
                "Apply Edit",
                variant="primary",
            )

            status = gr.Textbox(
                label="Status",
                interactive=False,
                lines=4,
            )

            gr.Markdown("### Change history")

            with gr.Row():
                undo_button = gr.Button("↩️ Undo", interactive=False)
                redo_button = gr.Button("↪️ Redo", interactive=False)

            with gr.Row():
                step_picker = gr.Dropdown(
                    label="Jump to version",
                    choices=[],
                    value=None,
                    interactive=True,
                )
                revert_button = gr.Button("Revert to selected version")

            history_view = gr.Markdown(
                "_No versions yet. Upload a video to begin._"
            )

    output_video = gr.Video(label="Current Version")
    download_file = gr.File(label="Download Current Version")

    # Order must match what _render() returns.
    render_outputs = [
        history_state,
        index_state,
        output_video,
        download_file,
        status,
        history_view,
        step_picker,
        undo_button,
        redo_button,
    ]

    upload_button.click(
        fn=upload_video,
        inputs=[input_video],
        outputs=render_outputs,
    )

    edit_button.click(
        fn=edit_video,
        inputs=[history_state, index_state, instruction],
        outputs=render_outputs + [instruction],
    )

    undo_button.click(
        fn=undo,
        inputs=[history_state, index_state],
        outputs=render_outputs,
    )

    redo_button.click(
        fn=redo,
        inputs=[history_state, index_state],
        outputs=render_outputs,
    )

    revert_button.click(
        fn=revert_to,
        inputs=[history_state, index_state, step_picker],
        outputs=render_outputs,
    )


if __name__ == "__main__":
    demo.launch(
        server_name=os.getenv("UI_HOST", "127.0.0.1"),
        server_port=int(os.getenv("UI_PORT", "7860")),
    )
