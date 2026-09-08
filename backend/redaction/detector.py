"""
Shared RapidOCR detection engine for RedactPro.

Provides a singleton OCR instance and a unified detection function
used by all file-type redactors (image, PDF, video).

The detection pipeline:
  1. Optionally resize image for faster OCR
  2. Run RapidOCR
  3. Filter results by confidence threshold
  4. Filter by digit count requirement
  5. Apply rule-based matching from rules.py
  6. Convert OCR polygons to padded bounding rectangles
  7. Remove duplicate detections via IoU / center-distance
"""

import cv2
import numpy as np
import logging

from rapidocr import RapidOCR

from .utils import (
    contains_number,
    digit_count,
    polygon_to_rect,
    remove_duplicate_detections,
)

from .rules import matches_any_rule


logger = logging.getLogger("redactpro.detector")


# ============================================================
# SINGLETON OCR INSTANCE
# ============================================================
# RapidOCR model loading is expensive. We load once at import
# time and reuse across all requests.

_ocr_instance = None


def get_ocr():
    """Get or create the singleton RapidOCR instance."""
    global _ocr_instance
    if _ocr_instance is None:
        logger.info("Loading RapidOCR engine...")
        _ocr_instance = RapidOCR()
        logger.info("RapidOCR engine loaded.")
    return _ocr_instance


# ============================================================
# DETECTION CONFIGURATION
# ============================================================

class DetectionConfig:
    """Configuration for the OCR detection pipeline."""

    def __init__(
        self,
        ocr_scale: float = 0.75,
        min_confidence: float = 0.35,
        min_digits: int = 1,
        padding_x: int = 5,
        padding_y: int = 4,
        use_rules: bool = True,
        custom_rules: dict = None,
        iou_threshold: float = 0.30,
        distance_threshold: float = 20.0,
    ):
        self.ocr_scale = ocr_scale
        self.min_confidence = min_confidence
        self.min_digits = min_digits
        self.padding_x = padding_x
        self.padding_y = padding_y
        self.use_rules = use_rules
        self.custom_rules = custom_rules
        self.iou_threshold = iou_threshold
        self.distance_threshold = distance_threshold


# Default configuration
DEFAULT_CONFIG = DetectionConfig()


# ============================================================
# MAIN DETECTION FUNCTION
# ============================================================

def detect_sensitive_regions(
    image: np.ndarray,
    config: DetectionConfig = None
) -> list:
    """
    Detect text regions containing sensitive information.

    Args:
        image: BGR numpy array (OpenCV format).
        config: Detection configuration. Uses defaults if None.

    Returns:
        List of [x, y, w, h, text, score] detections.
        Text and score are included for debugging but should
        NOT be logged in production for security reasons.
    """
    if config is None:
        config = DEFAULT_CONFIG

    ocr = get_ocr()

    original_height, original_width = image.shape[:2]

    # --------------------------------------------------------
    # Resize for OCR performance
    # --------------------------------------------------------

    if config.ocr_scale != 1.0:
        ocr_image = cv2.resize(
            image,
            None,
            fx=config.ocr_scale,
            fy=config.ocr_scale,
            interpolation=cv2.INTER_AREA
        )
    else:
        ocr_image = image

    # --------------------------------------------------------
    # Run RapidOCR
    # --------------------------------------------------------

    try:
        result = ocr(ocr_image)
    except Exception as error:
        logger.error("RapidOCR processing error: %s", type(error).__name__)
        return []

    if result is None:
        return []

    # --------------------------------------------------------
    # Extract results
    # --------------------------------------------------------

    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)

    if boxes is None or texts is None or scores is None:
        return []

    # --------------------------------------------------------
    # Process each detection
    # --------------------------------------------------------

    detections = []

    for box, text, score in zip(boxes, texts, scores):
        text = str(text).strip()

        if not text:
            continue

        # Confidence threshold
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue

        if score < config.min_confidence:
            continue

        # Rule-based filtering
        if config.custom_rules is not None:
            if not matches_any_rule(text, rules=config.custom_rules):
                continue
        else:
            # Must contain at least one digit
            if not contains_number(text):
                continue

            # Minimum digit count
            if digit_count(text) < config.min_digits:
                continue

            # Rule-based filtering (if enabled)
            if config.use_rules and not matches_any_rule(text):
                # If rules are enabled but text doesn't match any rule,
                # fall back to the basic digit-count filter.
                # This prevents redacting every single number (like "Page 1").
                if digit_count(text) < 3:
                    continue

        # Convert polygon to rectangle
        points = np.array(box, dtype=np.float32)

        rect = polygon_to_rect(
            points,
            config.ocr_scale,
            config.padding_x,
            config.padding_y,
            original_width,
            original_height
        )

        if rect is None:
            continue

        x, y, w, h = rect

        detections.append([x, y, w, h, text, score])

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    detections = remove_duplicate_detections(
        detections,
        iou_threshold=config.iou_threshold,
        distance_threshold=config.distance_threshold
    )

    # Log detection count only, never content
    logger.info("Detected %d sensitive regions", len(detections))

    return detections


def apply_redactions(
    image: np.ndarray,
    detections: list,
    color: tuple = (0, 0, 0)
) -> np.ndarray:
    """
    Apply solid-color redaction boxes to an image.

    Args:
        image: BGR numpy array to redact (modified in-place).
        detections: List of [x, y, w, h, ...] bounding boxes.
        color: BGR color tuple for redaction boxes.

    Returns:
        The modified image (same reference as input).
    """
    height, width = image.shape[:2]

    for detection in detections:
        x, y, w, h = detection[0], detection[1], detection[2], detection[3]

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(width, x + w)
        y2 = min(height, y + h)

        if x2 <= x1 or y2 <= y1:
            continue

        # Permanent solid redaction — no blur, no transparency
        image[y1:y2, x1:x2] = color

    return image
