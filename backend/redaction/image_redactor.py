"""
Image redaction module for RedactPro.

Handles PNG and JPG/JPEG files.
Refactored from the original blur_numbers_img.py script.

Pipeline:
  1. Load image via OpenCV
  2. Detect sensitive regions via shared detector
  3. Apply solid black redaction boxes
  4. Save output image
"""

import cv2
import logging

from .detector import (
    detect_sensitive_regions,
    apply_redactions,
    DetectionConfig,
)


logger = logging.getLogger("redactpro.image")


def redact_image(
    input_path: str,
    output_path: str,
    config: DetectionConfig = None
) -> dict:
    """
    Redact sensitive information from an image file.

    Args:
        input_path: Path to the input image (PNG, JPG, JPEG).
        output_path: Path to save the redacted image.
        config: Detection configuration. Uses defaults if None.

    Returns:
        dict with processing metadata:
            - detections: number of regions redacted
            - width: image width
            - height: image height

    Raises:
        FileNotFoundError: If input file doesn't exist.
        RuntimeError: If image cannot be read or written.
    """
    # --------------------------------------------------------
    # Load image
    # --------------------------------------------------------

    image = cv2.imread(input_path)

    if image is None:
        raise RuntimeError(
            "Could not read image file. "
            "The file may be corrupted or in an unsupported format."
        )

    height, width = image.shape[:2]

    logger.info(
        "Processing image: %dx%d",
        width, height
    )

    # --------------------------------------------------------
    # Detect sensitive regions
    # --------------------------------------------------------

    detections = detect_sensitive_regions(image, config)

    # --------------------------------------------------------
    # Apply redactions to a copy
    # --------------------------------------------------------

    output = image.copy()
    apply_redactions(output, detections)

    # --------------------------------------------------------
    # Save output
    # --------------------------------------------------------

    # Determine output format from extension
    ext = output_path.lower().rsplit(".", 1)[-1] if "." in output_path else "png"

    if ext in ("jpg", "jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, 95]
    else:
        params = [cv2.IMWRITE_PNG_COMPRESSION, 6]

    success = cv2.imwrite(output_path, output, params)

    if not success:
        raise RuntimeError(
            "Could not save redacted image."
        )

    logger.info(
        "Image redaction complete: %d regions redacted",
        len(detections)
    )

    return {
        "detections": len(detections),
        "width": width,
        "height": height,
    }
