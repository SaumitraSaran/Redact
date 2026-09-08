"""
RedactPro redaction package.

Provides a unified entry point for file redaction.
Routes files to the appropriate redactor based on type.
"""

import logging

from .detector import DetectionConfig, get_ocr
from .image_redactor import redact_image
from .pdf_redactor import redact_pdf
from .video_redactor import redact_video, get_video_duration
from .gemini_helper import get_custom_rules_from_instructions



logger = logging.getLogger("redactpro")


# ============================================================
# FILE TYPE ROUTING
# ============================================================

# Supported file types mapped to their redactor
SUPPORTED_TYPES = {
    "image": {
        "extensions": {".png", ".jpg", ".jpeg"},
        "mime_types": {"image/png", "image/jpeg"},
    },
    "pdf": {
        "extensions": {".pdf"},
        "mime_types": {"application/pdf"},
    },
    "video": {
        "extensions": {".mp4", ".mov"},
        "mime_types": {"video/mp4", "video/quicktime"},
    },
}


def get_file_type(extension: str) -> str:
    """
    Determine the file type category from extension.

    Args:
        extension: File extension including dot (e.g., ".png").

    Returns:
        Type string ("image", "pdf", "video") or None if unsupported.
    """
    ext = extension.lower()

    for file_type, info in SUPPORTED_TYPES.items():
        if ext in info["extensions"]:
            return file_type

    return None


def get_supported_extensions() -> set:
    """Get all supported file extensions."""
    extensions = set()
    for info in SUPPORTED_TYPES.values():
        extensions.update(info["extensions"])
    return extensions


def get_supported_mime_types() -> set:
    """Get all supported MIME types."""
    mime_types = set()
    for info in SUPPORTED_TYPES.values():
        mime_types.update(info["mime_types"])
    return mime_types


def redact_file(
    input_path: str,
    output_path: str,
    file_type: str,
    instructions: str = None,
    config: DetectionConfig = None,
    progress_callback = None
) -> dict:
    """
    Unified file redaction entry point.

    Routes to the appropriate redactor based on file_type.

    Args:
        input_path: Path to the uploaded file.
        output_path: Path for the redacted output.
            For videos, this is used as the output directory.
        file_type: One of "image", "pdf", "video".
        instructions: User-provided instructions (reserved for future use).
        config: Detection configuration. Uses defaults if None.
        progress_callback: Optional callback for progress reporting.

    Returns:
        dict with type-specific processing metadata.

    Raises:
        ValueError: If file_type is unsupported.
        RuntimeError: If processing fails.
    """
    if instructions and file_type != "video":
        logger.info("Processing custom instructions via Gemini")
        custom_rules = get_custom_rules_from_instructions(instructions)
        if custom_rules:
            if config is None:
                from .detector import DetectionConfig
                config = DetectionConfig()
            config.custom_rules = custom_rules
            logger.info(f"Custom rules generated: {list(custom_rules.keys())}")

    if file_type == "image":
        return redact_image(input_path, output_path, config)

    elif file_type == "pdf":
        return redact_pdf(input_path, output_path, config)

    elif file_type == "video":
        return redact_video(input_path, output_path, config, progress_callback=progress_callback)

    else:
        raise ValueError(f"Unsupported file type: {file_type}")
