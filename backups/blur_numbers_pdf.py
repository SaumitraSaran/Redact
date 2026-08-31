import fitz
import cv2
import numpy as np
import re
import os
import time

from rapidocr import RapidOCR


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_PDF = "input.pdf"
OUTPUT_PDF = "redacted_output.pdf"


# ============================================================
# PDF RENDERING
# ============================================================

# Resolution used when converting PDF pages into images.
#
# Higher DPI:
#   Better OCR
#   Slower
#   Larger temporary images
#
# Lower DPI:
#   Faster
#   Potentially worse OCR
#
# 150 is a good starting point.
PDF_DPI = 150


# ============================================================
# OCR SETTINGS
# ============================================================

# Scale the rendered page before OCR.
#
# 1.0 = original rendered size
# 0.75 = faster
# 0.50 = much faster
#
# For PDFs I recommend 0.75 or 1.0.
OCR_SCALE = 0.75


# Minimum OCR confidence.
#
# Lower:
#   Catches more numbers
#   More false positives
#
# Higher:
#   Cleaner results
#   Can miss numbers
#
# 0.35 is a good starting point.
MIN_TEXT_CONFIDENCE = 0.35


# ============================================================
# NUMBER FILTERING
# ============================================================

# Minimum number of digits required.
#
# 1 means:
#
#   "7"       -> redact
#   "42"      -> redact
#   "12345"   -> redact
#
# If you only want multi-digit numbers:
#
#   MIN_DIGITS = 2
#
MIN_DIGITS = 1


# ============================================================
# REDACTION BOX
# ============================================================

# Extra space around the detected number.
#
# Smaller values = tighter boxes.
#
# For example:
#
# PADDING_X = 5
# PADDING_Y = 4
#
PADDING_X = 5
PADDING_Y = 4


# Solid black.
REDACTION_COLOR = (
    0,
    0,
    0
)


# ============================================================
# LOAD RAPIDOCR
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
# OCR DETECTION
# ============================================================

def detect_numbers(image):

    original_height, original_width = (
        image.shape[:2]
    )

    # --------------------------------------------------------
    # Resize for OCR
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
    # Run RapidOCR
    # --------------------------------------------------------

    try:

        result = ocr(
            ocr_image
        )

    except Exception as error:

        print()
        print(
            "RapidOCR error:",
            error
        )

        return []

    if result is None:

        return []

    # --------------------------------------------------------
    # Extract RapidOCR result
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
        # Does OCR text contain a digit?
        # ----------------------------------------------------

        if not contains_number(
            text
        ):

            continue

        # ----------------------------------------------------
        # Confidence
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
        # Number of digits
        # ----------------------------------------------------

        if (
            digit_count(text)
            <
            MIN_DIGITS
        ):

            continue

        # ----------------------------------------------------
        # Convert OCR polygon into rectangle
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
        # Convert OCR coordinates back to original image size
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
        # Add padding
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
        # Clamp box
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
# REDACT IMAGE
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
    # Padding
    # --------------------------------------------------------

    x1 = max(
        0,
        x
    )

    y1 = max(
        0,
        y
    )

    x2 = min(
        width,
        x + w
    )

    y2 = min(
        height,
        y + h
    )

    if (
        x2 <= x1
        or
        y2 <= y1
    ):

        return

    # --------------------------------------------------------
    # SOLID BLACK REDACTION
    # --------------------------------------------------------

    image[
        y1:y2,
        x1:x2
    ] = REDACTION_COLOR


# ============================================================
# PROCESS PDF
# ============================================================

def main():

    # ========================================================
    # CHECK FILE
    # ========================================================

    if not os.path.exists(
        INPUT_PDF
    ):

        raise FileNotFoundError(
            f"Input PDF not found:\n"
            f"{INPUT_PDF}"
        )

    # ========================================================
    # OPEN PDF
    # ========================================================

    document = fitz.open(
        INPUT_PDF
    )

    page_count = len(
        document
    )

    print()
    print("=" * 70)
    print("RAPIDOCR PDF NUMBER REDACTION")
    print("=" * 70)

    print(
        f"Input PDF : "
        f"{INPUT_PDF}"
    )

    print(
        f"Pages     : "
        f"{page_count}"
    )

    print(
        f"DPI       : "
        f"{PDF_DPI}"
    )

    print(
        f"OCR Scale : "
        f"{OCR_SCALE}"
    )

    print(
        f"Confidence: "
        f"{MIN_TEXT_CONFIDENCE}"
    )

    print(
        f"Min digits: "
        f"{MIN_DIGITS}"
    )

    print()

    start_time = time.time()

    total_redactions = 0

    # ========================================================
    # PROCESS EACH PAGE
    # ========================================================

    for page_number in range(
        page_count
    ):

        page = document[
            page_number
        ]

        print(
            f"\nProcessing page "
            f"{page_number + 1}/"
            f"{page_count}..."
        )

        # ====================================================
        # RENDER PAGE
        # ====================================================

        zoom = (
            PDF_DPI /
            72.0
        )

        matrix = fitz.Matrix(
            zoom,
            zoom
        )

        pixmap = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        # ====================================================
        # CONVERT PDF PAGE TO OPENCV IMAGE
        # ====================================================

        image = np.frombuffer(
            pixmap.samples,
            dtype=np.uint8
        )

        image = image.reshape(
            pixmap.height,
            pixmap.width,
            pixmap.n
        )

        # PDF rendering is RGB.
        # OpenCV expects BGR.
        image = cv2.cvtColor(
            image,
            cv2.COLOR_RGB2BGR
        )

        # ====================================================
        # OCR
        # ====================================================

        detections = detect_numbers(
            image
        )

        print(
            f"Numbers detected: "
            f"{len(detections)}"
        )

        # ====================================================
        # SHOW DETECTIONS
        # ====================================================

        for index, detection in enumerate(
            detections,
            start=1
        ):

            x, y, w, h, text, score = (
                detection
            )

            print(
                f"  {index}. "
                f"'{text}' "
                f"| confidence "
                f"{score:.2f}"
            )

        # ====================================================
        # REDACT
        # ====================================================

        for detection in detections:

            redact_detection(
                image,
                detection
            )

        total_redactions += len(
            detections
        )

        # ====================================================
        # CONVERT BACK TO RGB
        # ====================================================

        image_rgb = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2RGB
        )

        # ====================================================
        # CREATE PDF IMAGE
        # ====================================================

        success, encoded = cv2.imencode(
            ".png",
            cv2.cvtColor(
                image_rgb,
                cv2.COLOR_RGB2BGR
            )
        )

        if not success:

            raise RuntimeError(
                f"Could not encode "
                f"page {page_number + 1}"
            )

        # ====================================================
        # REPLACE PAGE CONTENT
        # ====================================================

        # Create a new PDF page with
        # the original page dimensions.

        new_page = page

        # Remove existing content by
        # creating a new document page
        # is more complicated, so we
        # cover the original page with
        # the redacted rendered image.

        rect = page.rect

        new_page.insert_image(
            rect,
            stream=encoded.tobytes(),
            keep_proportion=False,
            overlay=True
        )

        # ====================================================
        # PROGRESS
        # ====================================================

        elapsed = (
            time.time()
            -
            start_time
        )

        print(
            f"Elapsed: "
            f"{elapsed:.1f}s"
        )

    # ========================================================
    # SAVE
    # ========================================================

    print()
    print(
        "Saving redacted PDF..."
    )

    document.save(
        OUTPUT_PDF,
        garbage=4,
        deflate=True
    )

    document.close()

    # ========================================================
    # DONE
    # ========================================================

    elapsed = (
        time.time()
        -
        start_time
    )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print(
        f"Output PDF: "
        f"{OUTPUT_PDF}"
    )

    print(
        f"Pages: "
        f"{page_count}"
    )

    print(
        f"Total redactions: "
        f"{total_redactions}"
    )

    print(
        f"Processing time: "
        f"{elapsed:.2f} seconds"
    )

    print("=" * 70)
    print()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()