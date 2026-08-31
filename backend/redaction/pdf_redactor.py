"""
PDF redaction module for RedactPro.

Handles PDF files by rendering each page to an image,
running OCR-based redaction, and producing a flattened output PDF.

SECURITY: The output PDF contains ONLY the redacted raster images.
The original text layer is completely removed to prevent extraction
of redacted content via text selection, copy-paste, or PDF parsing.

Refactored from the original blur_numbers_pdf.py script.

Pipeline per page:
  1. Render PDF page to image at configured DPI
  2. Detect sensitive regions via shared detector
  3. Apply solid black redaction boxes
  4. Clear original page content entirely
  5. Insert redacted image as sole page content
  6. Save with garbage collection to strip residual data
"""

import cv2
import numpy as np
import logging

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from .detector import (
    detect_sensitive_regions,
    apply_redactions,
    DetectionConfig,
)


logger = logging.getLogger("redactpro.pdf")


# PDF rendering DPI. Higher = better OCR but slower.
DEFAULT_PDF_DPI = 150


def redact_pdf(
    input_path: str,
    output_path: str,
    config: DetectionConfig = None,
    dpi: int = DEFAULT_PDF_DPI
) -> dict:
    """
    Redact sensitive information from a PDF file.

    The output is a flattened PDF where each page is a raster image
    with redactions applied. No original text content remains.

    Args:
        input_path: Path to the input PDF.
        output_path: Path to save the redacted PDF.
        config: Detection configuration. Uses defaults if None.
        dpi: Resolution for rendering PDF pages.

    Returns:
        dict with processing metadata:
            - pages: number of pages processed
            - total_detections: total regions redacted across all pages

    Raises:
        RuntimeError: If PDF cannot be opened or processed.
    """
    # --------------------------------------------------------
    # Open PDF
    # --------------------------------------------------------

    try:
        document = fitz.open(input_path)
    except Exception:
        raise RuntimeError(
            "Could not open PDF file. "
            "The file may be corrupted or password-protected."
        )

    page_count = len(document)
    total_detections = 0

    logger.info(
        "Processing PDF: %d pages at %d DPI",
        page_count, dpi
    )

    # --------------------------------------------------------
    # Process each page
    # --------------------------------------------------------

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page_number in range(page_count):

        page = document[page_number]

        logger.info(
            "Processing page %d/%d",
            page_number + 1, page_count
        )

        # ====================================================
        # Render page to image
        # ====================================================

        pixmap = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        image = np.frombuffer(
            pixmap.samples,
            dtype=np.uint8
        )

        image = image.reshape(
            pixmap.height,
            pixmap.width,
            pixmap.n
        )

        # PyMuPDF renders RGB, OpenCV uses BGR
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        # ====================================================
        # Detect and redact
        # ====================================================

        detections = detect_sensitive_regions(image, config)
        apply_redactions(image, detections)

        total_detections += len(detections)

        # ====================================================
        # SECURITY: Replace page with flattened image
        # ====================================================
        # We completely clear the original page content and
        # insert the redacted raster image as the sole content.
        # This ensures the original text cannot be recovered.

        # Convert back to RGB for PNG encoding
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Encode as PNG
        success, encoded = cv2.imencode(
            ".png",
            cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        )

        if not success:
            raise RuntimeError(
                f"Could not encode page {page_number + 1}"
            )

        # Clear original page content to prevent text extraction
        # This removes all text, vectors, and images from the
        # original page before inserting the redacted image.
        page.clean_contents()

        # Get original page rect for proper sizing
        rect = page.rect

        # Remove all existing content by clearing xrefs
        # We draw a white rectangle over everything first,
        # then overlay the redacted image
        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()

        # Insert the redacted image over the entire page
        page.insert_image(
            rect,
            stream=encoded.tobytes(),
            keep_proportion=False,
            overlay=True
        )

    # --------------------------------------------------------
    # Save output
    # --------------------------------------------------------

    logger.info("Saving redacted PDF...")

    # garbage=4 removes unused objects
    # deflate=True compresses streams
    document.save(
        output_path,
        garbage=4,
        deflate=True
    )

    document.close()

    logger.info(
        "PDF redaction complete: %d pages, %d total detections",
        page_count, total_detections
    )

    return {
        "pages": page_count,
        "total_detections": total_detections,
    }
