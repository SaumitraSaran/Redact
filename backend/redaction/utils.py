"""
Shared geometry and text utility functions for redaction detection.

Extracted from the original blur_numbers_img.py, blur_numbers_vid.py,
and blur_numbers_pdf.py scripts to avoid duplication.
"""

import re
import numpy as np


def contains_number(text: str) -> bool:
    """Check if text contains at least one digit."""
    return bool(re.search(r"\d", text))


def digit_count(text: str) -> int:
    """Count the number of digits in text."""
    return len(re.findall(r"\d", text))


def calculate_iou(a: list, b: list) -> float:
    """
    Calculate Intersection over Union between two bounding boxes.

    Each box is [x, y, w, h, ...] where x, y is top-left corner.
    """
    ax1 = a[0]
    ay1 = a[1]
    ax2 = a[0] + a[2]
    ay2 = a[1] + a[3]

    bx1 = b[0]
    by1 = b[1]
    bx2 = b[0] + b[2]
    by2 = b[1] + b[3]

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)

    intersection = iw * ih
    area_a = a[2] * a[3]
    area_b = b[2] * b[3]
    union = area_a + area_b - intersection

    if union <= 0:
        return 0.0

    return intersection / union


def center_distance(a: list, b: list) -> float:
    """
    Calculate Euclidean distance between centers of two bounding boxes.

    Each box is [x, y, w, h, ...].
    """
    ax = a[0] + a[2] / 2
    ay = a[1] + a[3] / 2
    bx = b[0] + b[2] / 2
    by = b[1] + b[3] / 2

    return float(np.sqrt((ax - bx) ** 2 + (ay - by) ** 2))


def remove_duplicate_detections(
    detections: list,
    iou_threshold: float = 0.30,
    distance_threshold: float = 20.0
) -> list:
    """
    Remove duplicate detections using IoU overlap and center distance.

    Keeps higher-confidence detections first.
    Each detection is [x, y, w, h, text, score].
    """
    detections.sort(
        key=lambda item: item[5],
        reverse=True
    )

    final = []

    for detection in detections:
        duplicate = False

        for existing in final:
            overlap = calculate_iou(detection, existing)
            distance = center_distance(detection, existing)

            if overlap > iou_threshold:
                duplicate = True
                break

            if distance < distance_threshold:
                duplicate = True
                break

        if not duplicate:
            final.append(detection)

    return final


def polygon_to_rect(
    points: np.ndarray,
    ocr_scale: float,
    padding_x: int,
    padding_y: int,
    image_width: int,
    image_height: int
) -> tuple:
    """
    Convert an OCR polygon to a padded, clamped bounding rectangle.

    Returns (x, y, w, h) or None if the resulting box is too small.
    """
    x_min = float(np.min(points[:, 0]))
    y_min = float(np.min(points[:, 1]))
    x_max = float(np.max(points[:, 0]))
    y_max = float(np.max(points[:, 1]))

    # Scale back to original resolution
    x = int(x_min / ocr_scale)
    y = int(y_min / ocr_scale)
    w = int((x_max - x_min) / ocr_scale)
    h = int((y_max - y_min) / ocr_scale)

    if w <= 2 or h <= 2:
        return None

    # Add padding
    x -= padding_x
    y -= padding_y
    w += padding_x * 2
    h += padding_y * 2

    # Clamp to image bounds
    x = max(0, x)
    y = max(0, y)
    w = min(w, image_width - x)
    h = min(h, image_height - y)

    if w <= 0 or h <= 0:
        return None

    return (x, y, w, h)
