import cv2
import numpy as np
import re
import os
import time

from rapidocr import RapidOCR


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_IMAGE = "input." + "png" or "jpg"
OUTPUT_IMAGE = "redacted_image.png"


# ============================================================
# OCR SETTINGS
# ============================================================

# Resize image ONLY for OCR.
#
# 1.00 = original resolution
# 0.75 = faster
# 0.50 = much faster
#
# For images, I recommend starting with 0.75.
OCR_SCALE = 0.75


# Minimum RapidOCR confidence.
#
# Lower = catches more possible text
# Higher = fewer false positives
MIN_TEXT_CONFIDENCE = 0.35


# ============================================================
# NUMBER FILTERING
# ============================================================

# Number of digits required.
#
# 1:
#     "7" gets redacted
#
# 2:
#     "42" gets redacted
#
# 3:
#     "123" gets redacted
#
# Keep this at 1 if confidential numbers can be single digits.
MIN_DIGITS = 1


# ============================================================
# REDACTION
# ============================================================

# Safety padding around detected text.
PADDING_X = 2
PADDING_Y = 1


# Solid black.
REDACTION_COLOR = (
    0,
    0,
    0
)


# ============================================================
# RAPIDOCR
# ============================================================

print()
print("Loading RapidOCR...")

ocr = RapidOCR()

print("RapidOCR loaded.")
print()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def contains_number(text):

    return bool(
        re.search(
            r"\d",
            text
        )
    )


def digit_count(text):

    return len(
        re.findall(
            r"\d",
            text
        )
    )


def calculate_iou(a, b):

    ax1 = a[0]
    ay1 = a[1]

    ax2 = a[0] + a[2]
    ay2 = a[1] + a[3]

    bx1 = b[0]
    by1 = b[1]

    bx2 = b[0] + b[2]
    by2 = b[1] + b[3]

    ix1 = max(
        ax1,
        bx1
    )

    iy1 = max(
        ay1,
        by1
    )

    ix2 = min(
        ax2,
        bx2
    )

    iy2 = min(
        ay2,
        by2
    )

    iw = max(
        0,
        ix2 - ix1
    )

    ih = max(
        0,
        iy2 - iy1
    )

    intersection = (
        iw * ih
    )

    area_a = (
        a[2] *
        a[3]
    )

    area_b = (
        b[2] *
        b[3]
    )

    union = (
        area_a +
        area_b -
        intersection
    )

    if union <= 0:

        return 0.0

    return (
        intersection /
        union
    )


def center_distance(a, b):

    ax = (
        a[0] +
        a[2] / 2
    )

    ay = (
        a[1] +
        a[3] / 2
    )

    bx = (
        b[0] +
        b[2] / 2
    )

    by = (
        b[1] +
        b[3] / 2
    )

    return np.sqrt(
        (ax - bx) ** 2 +
        (ay - by) ** 2
    )


# ============================================================
# RAPIDOCR DETECTION
# ============================================================

def detect_numbers(image):

    original_height, original_width = (
        image.shape[:2]
    )

    # --------------------------------------------------------
    # Create OCR image.
    # --------------------------------------------------------

    if OCR_SCALE != 1.0:

        ocr_image = cv2.resize(
            image,
            None,
            fx=OCR_SCALE,
            fy=OCR_SCALE,
            interpolation=cv2.INTER_AREA
        )

    else:

        ocr_image = image

    # --------------------------------------------------------
    # Run RapidOCR.
    # --------------------------------------------------------

    try:

        result = ocr(
            ocr_image
        )

    except Exception as error:

        print()
        print(
            "RapidOCR error:"
        )

        print(error)

        return []

    # --------------------------------------------------------
    # Empty result.
    # --------------------------------------------------------

    if result is None:

        return []

    # --------------------------------------------------------
    # Current RapidOCR result format.
    # --------------------------------------------------------

    boxes = getattr(
        result,
        "boxes",
        None
    )

    texts = getattr(
        result,
        "txts",
        None
    )

    scores = getattr(
        result,
        "scores",
        None
    )

    if boxes is None:
        return []

    if texts is None:
        return []

    if scores is None:
        return []

    detections = []

    # ========================================================
    # PROCESS OCR RESULTS
    # ========================================================

    for box, text, score in zip(
        boxes,
        texts,
        scores
    ):

        text = str(
            text
        ).strip()

        if not text:

            continue

        # ----------------------------------------------------
        # Must contain a number.
        # ----------------------------------------------------

        if not contains_number(
            text
        ):

            continue

        # ----------------------------------------------------
        # Confidence.
        # ----------------------------------------------------

        try:

            score = float(
                score
            )

        except (
            TypeError,
            ValueError
        ):

            continue

        if (
            score <
            MIN_TEXT_CONFIDENCE
        ):

            continue

        # ----------------------------------------------------
        # Digit count.
        # ----------------------------------------------------

        if (
            digit_count(text)
            <
            MIN_DIGITS
        ):

            continue

        # ----------------------------------------------------
        # Convert RapidOCR polygon to rectangle.
        # ----------------------------------------------------

        points = np.array(
            box,
            dtype=np.float32
        )

        x_min = float(
            np.min(
                points[:, 0]
            )
        )

        y_min = float(
            np.min(
                points[:, 1]
            )
        )

        x_max = float(
            np.max(
                points[:, 0]
            )
        )

        y_max = float(
            np.max(
                points[:, 1]
            )
        )

        # ----------------------------------------------------
        # Convert OCR coordinates back to original resolution.
        # ----------------------------------------------------

        x = int(
            x_min /
            OCR_SCALE
        )

        y = int(
            y_min /
            OCR_SCALE
        )

        w = int(
            (
                x_max -
                x_min
            )
            /
            OCR_SCALE
        )

        h = int(
            (
                y_max -
                y_min
            )
            /
            OCR_SCALE
        )

        if w <= 2 or h <= 2:

            continue

        # ----------------------------------------------------
        # Safety padding.
        # ----------------------------------------------------

        x -= PADDING_X
        y -= PADDING_Y

        w += (
            PADDING_X *
            2
        )

        h += (
            PADDING_Y *
            2
        )

        # ----------------------------------------------------
        # Clamp to image.
        # ----------------------------------------------------

        x = max(
            0,
            x
        )

        y = max(
            0,
            y
        )

        w = min(
            w,
            original_width - x
        )

        h = min(
            h,
            original_height - y
        )

        if w <= 0 or h <= 0:

            continue

        detections.append(
            [
                x,
                y,
                w,
                h,
                text,
                score
            ]
        )

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    detections.sort(
        key=lambda item:
            item[5],
        reverse=True
    )

    final_detections = []

    for detection in detections:

        duplicate = False

        for existing in (
            final_detections
        ):

            overlap = calculate_iou(
                detection,
                existing
            )

            distance = center_distance(
                detection,
                existing
            )

            if overlap > 0.30:

                duplicate = True

                break

            if distance < 20:

                duplicate = True

                break

        if not duplicate:

            final_detections.append(
                detection
            )

    return final_detections


# ============================================================
# REDACT DETECTION
# ============================================================

def redact_detection(
    image,
    detection
):

    height, width = (
        image.shape[:2]
    )

    x = detection[0]
    y = detection[1]
    w = detection[2]
    h = detection[3]

    # --------------------------------------------------------
    # Additional safety padding.
    # --------------------------------------------------------

    x1 = max(
        0,
        x -
        PADDING_X
    )

    y1 = max(
        0,
        y -
        PADDING_Y
    )

    x2 = min(
        width,
        x +
        w +
        PADDING_X
    )

    y2 = min(
        height,
        y +
        h +
        PADDING_Y
    )

    if (
        x2 <= x1
        or
        y2 <= y1
    ):

        return

    # --------------------------------------------------------
    # SOLID REDACTION
    # --------------------------------------------------------

    image[
        y1:y2,
        x1:x2
    ] = REDACTION_COLOR


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # CHECK INPUT
    # ========================================================

    if not os.path.exists(
        INPUT_IMAGE
    ):

        raise FileNotFoundError(
            f"Input image not found:\n"
            f"{INPUT_IMAGE}"
        )

    # ========================================================
    # LOAD IMAGE
    # ========================================================

    image = cv2.imread(
        INPUT_IMAGE
    )

    if image is None:

        raise RuntimeError(
            f"Could not read image:\n"
            f"{INPUT_IMAGE}"
        )

    height, width = (
        image.shape[:2]
    )

    # ========================================================
    # INFORMATION
    # ========================================================

    print()
    print("=" * 70)
    print("RAPIDOCR IMAGE REDACTION")
    print("=" * 70)

    print(
        f"Input      : "
        f"{INPUT_IMAGE}"
    )

    print(
        f"Resolution : "
        f"{width} x {height}"
    )

    print(
        f"OCR scale  : "
        f"{OCR_SCALE}"
    )

    print(
        f"Confidence : "
        f"{MIN_TEXT_CONFIDENCE}"
    )

    print()

    # ========================================================
    # OCR
    # ========================================================

    start_time = time.time()

    print(
        "Detecting numbers..."
    )

    detections = detect_numbers(
        image
    )

    detection_time = (
        time.time()
        -
        start_time
    )

    # ========================================================
    # DETECTION RESULTS
    # ========================================================

    print()

    print(
        f"Detected "
        f"{len(detections)} "
        f"number-containing text regions."
    )

    print()

    if detections:

        print(
            "Detected text:"
        )

        print(
            "-" * 50
        )

        for index, detection in enumerate(
            detections,
            start=1
        ):

            x, y, w, h, text, score = (
                detection
            )

            print(
                f"{index}. "
                f"'{text}' "
                f"| confidence: "
                f"{score:.2f} "
                f"| box: "
                f"({x}, {y}, "
                f"{w}, {h})"
            )

        print()

    else:

        print(
            "No numbers detected."
        )

        print()

    # ========================================================
    # REDACT
    # ========================================================

    print(
        "Applying redactions..."
    )

    output = image.copy()

    for detection in detections:

        redact_detection(
            output,
            detection
        )

    # ========================================================
    # SAVE
    # ========================================================

    success = cv2.imwrite(
        OUTPUT_IMAGE,
        output
    )

    if not success:

        raise RuntimeError(
            f"Could not save output:\n"
            f"{OUTPUT_IMAGE}"
        )

    total_time = (
        time.time()
        -
        start_time
    )

    # ========================================================
    # DONE
    # ========================================================

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print(
        f"Output: "
        f"{OUTPUT_IMAGE}"
    )

    print(
        f"Numbers redacted: "
        f"{len(detections)}"
    )

    print(
        f"Processing time: "
        f"{total_time:.2f} seconds"
    )

    print("=" * 70)
    print()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()