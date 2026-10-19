
import re

TIME_PATTERN = r"\d+(?:\.\d+)?"


class MultipleInstructionsError(ValueError):
    """Raised when one message contains more than one editing instruction."""


# Action verbs the parser understands. "cut out" counts once because only
# the word "cut" is matched.
ACTION_PATTERN = re.compile(
    r"\b(?:trim|cut|remove|delete|add|generate|create|make|burn|embed)\b",
    re.IGNORECASE,
)

# Words/characters that usually chain several instructions together.
SEQUENCE_PATTERN = re.compile(
    r";|\b(?:and then|after that|afterwards|then)\b",
    re.IGNORECASE,
)

SUBTITLE_PATTERN = re.compile(
    r"\b(?:add|generate|create|make|burn|embed)\b"
    r".*\b(?:subtitles?|captions?)\b"
    r"|\b(?:subtitle|caption)\s+"
    r"(?:this|the)\s+video\b",
    re.IGNORECASE,
)

REMOVE_PATTERN = re.compile(
    rf"\bremove\b.*?\bfrom\s+({TIME_PATTERN})\s*"
    rf"(?:seconds?|secs?|s)?\s+"
    rf"\bto\s+({TIME_PATTERN})\s*"
    rf"(?:seconds?|secs?|s)?\b",
    re.IGNORECASE,
)

REMOVE_FIRST_PATTERN = re.compile(
    rf"\b(?:remove|cut out|delete)\s+"
    rf"(?:the\s+)?first\s+({TIME_PATTERN})\s*"
    rf"(?:seconds?|secs?|s)\b",
    re.IGNORECASE,
)

TRIM_PATTERNS = [
    re.compile(
        rf"\btrim\b.*?\bfrom\s+({TIME_PATTERN})\s*"
        rf"(?:seconds?|secs?|s)?\s+"
        rf"\bto\s+({TIME_PATTERN})\s*"
        rf"(?:seconds?|secs?|s)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bcut\b.*?\bfrom\s+({TIME_PATTERN})\s*"
        rf"(?:seconds?|secs?|s)?\s+"
        rf"\bto\s+({TIME_PATTERN})\s*"
        rf"(?:seconds?|secs?|s)?\b",
        re.IGNORECASE,
    ),
]


def ensure_single_instruction(instruction: str) -> None:
    """Reject messages that bundle several edits into one instruction."""
    non_empty_lines = [
        line for line in instruction.splitlines() if line.strip()
    ]
    action_count = len(ACTION_PATTERN.findall(instruction))

    if (
        len(non_empty_lines) > 1
        or action_count > 1
        or SEQUENCE_PATTERN.search(instruction)
    ):
        raise MultipleInstructionsError(
            "That looks like more than one instruction. "
            "Please send one instruction at a time, for example "
            "'Trim the video from 1 second to 3 seconds.' "
            "You can undo or redo any change afterwards."
        )


def parse_instruction(instruction: str) -> dict:
    """Convert a supported plain-English instruction into an edit plan."""

    if not instruction or not instruction.strip():
        raise ValueError("Instruction cannot be empty.")

    instruction = instruction.strip()

    # Only one edit per request so nothing is silently ignored.
    ensure_single_instruction(instruction)

    # Handle subtitle-generation instructions.
    if SUBTITLE_PATTERN.search(instruction):
        return {
            "operation": "add_subtitles",
        }

    # Handle instructions like "remove the first 2 seconds".
    match = REMOVE_FIRST_PATTERN.search(instruction)

    if match:
        end_seconds = float(match.group(1))

        if end_seconds <= 0:
            raise ValueError("Removal time must be greater than zero.")

        return {
            "operation": "remove_section",
            "start_seconds": 0.0,
            "end_seconds": end_seconds,
        }

    # Check section removal first.
    match = REMOVE_PATTERN.search(instruction)

    if match:
        start_seconds = float(match.group(1))
        end_seconds = float(match.group(2))

        if end_seconds <= start_seconds:
            raise ValueError(
                "End time must be greater than start time."
            )

        return {
            "operation": "remove_section",
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
        }

    # Check trim instructions.
    for pattern in TRIM_PATTERNS:
        match = pattern.search(instruction)

        if match:
            start_seconds = float(match.group(1))
            end_seconds = float(match.group(2))

            if end_seconds <= start_seconds:
                raise ValueError(
                    "End time must be greater than start time."
                )

            return {
                "operation": "trim",
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
            }

    raise ValueError(
        "I couldn't understand that instruction yet. "
        "Try: 'Trim the video from 1 second to 3 seconds.'"
    )
