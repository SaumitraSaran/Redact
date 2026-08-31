import cv2
import numpy as np
import re
import time
import os
import math

from rapidocr import RapidOCR


INPUT_VIDEO = "input.mp4"

OUTPUT_DIR = "redacted_output"

MAX_VIDEO_DURATION = 10.0

OCR_INTERVAL = 3

OCR_SCALE = 0.50

MIN_TEXT_CONFIDENCE = 0.35

MIN_DIGITS = 1

# ============================================================
# REDACTION
# ============================================================

PADDING_X = 2
PADDING_Y = 1

# Solid black redaction.
REDACTION_COLOR = (0, 0, 0)


# ============================================================
# TRACKING
# ============================================================

TRACK_SEARCH_MARGIN = 100

TRACK_THRESHOLD = 0.55

MAX_LOST_FRAMES = 6

# ============================================================
# RAPIDOCR
# ============================================================

print()
print("Loading RapidOCR...")

ocr = RapidOCR()

print("RapidOCR loaded.")
print()


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
# RAPIDOCR NUMBER DETECTION
# ============================================================

def detect_numbers(frame):

    original_height, original_width = (
        frame.shape[:2]
    )

    if OCR_SCALE != 1.0:

        ocr_frame = cv2.resize(
            frame,
            None,
            fx=OCR_SCALE,
            fy=OCR_SCALE,
            interpolation=cv2.INTER_AREA
        )

    else:

        ocr_frame = frame

    try:

        result = ocr(
            ocr_frame
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

        if not contains_number(
            text
        ):

            continue

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

        if (
            digit_count(text)
            <
            MIN_DIGITS
        ):

            continue

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

class NumberTrack:

    def __init__(
        self,
        frame,
        detection
    ):

        self.x = float(
            detection[0]
        )

        self.y = float(
            detection[1]
        )

        self.w = float(
            detection[2]
        )

        self.h = float(
            detection[3]
        )

        self.text = (
            detection[4]
        )

        self.confidence = (
            detection[5]
        )

        self.lost = 0

        self.template = (
            self.create_template(
                frame
            )
        )

    def create_template(
        self,
        frame
    ):

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        frame_height, frame_width = (
            gray.shape
        )

        x1 = max(
            0,
            int(self.x)
        )

        y1 = max(
            0,
            int(self.y)
        )

        x2 = min(
            frame_width,
            int(
                self.x +
                self.w
            )
        )

        y2 = min(
            frame_height,
            int(
                self.y +
                self.h
            )
        )

        if (
            x2 <= x1
            or
            y2 <= y1
        ):

            return None

        template = gray[
            y1:y2,
            x1:x2
        ]

        if template.size == 0:

            return None

        return template.copy()

    def update(
        self,
        frame
    ):

        if self.template is None:

            self.lost += 1

            return False

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        frame_height, frame_width = (
            gray.shape
        )

        old_x = int(
            self.x
        )

        old_y = int(
            self.y
        )

        search_x1 = max(
            0,
            old_x -
            TRACK_SEARCH_MARGIN
        )

        search_y1 = max(
            0,
            old_y -
            TRACK_SEARCH_MARGIN
        )

        search_x2 = min(
            frame_width,
            old_x +
            int(self.w) +
            TRACK_SEARCH_MARGIN
        )

        search_y2 = min(
            frame_height,
            old_y +
            int(self.h) +
            TRACK_SEARCH_MARGIN
        )

        search = gray[
            search_y1:search_y2,
            search_x1:search_x2
        ]

        template_height, template_width = (
            self.template.shape
        )

        if (
            search.shape[0]
            <
            template_height
            or
            search.shape[1]
            <
            template_width
        ):

            self.lost += 1

            return False

        result = cv2.matchTemplate(
            search,
            self.template,
            cv2.TM_CCOEFF_NORMED
        )

        _, confidence, _, location = (
            cv2.minMaxLoc(
                result
            )
        )

        if (
            confidence <
            TRACK_THRESHOLD
        ):

            self.lost += 1

            return False

        self.x = (
            search_x1 +
            location[0]
        )

        self.y = (
            search_y1 +
            location[1]
        )

        self.lost = 0

        return True

def update_tracks(
    tracks,
    detections,
    frame
):

    matched = set()

    for detection in detections:

        best_index = None

        best_score = -1

        for index, track in enumerate(
            tracks
        ):

            if index in matched:

                continue

            track_box = [
                track.x,
                track.y,
                track.w,
                track.h,
                track.text,
                track.confidence
            ]

            overlap = calculate_iou(
                detection,
                track_box
            )

            distance = center_distance(
                detection,
                track_box
            )

            if overlap > 0.10:

                score = (
                    overlap * 100
                )

            elif distance < 100:

                score = (
                    10 -
                    (
                        distance /
                        100
                    )
                )

            else:

                continue

            if score > best_score:

                best_score = score

                best_index = index

        if best_index is not None:

            track = tracks[
                best_index
            ]

            track.x = detection[0]
            track.y = detection[1]
            track.w = detection[2]
            track.h = detection[3]

            track.text = detection[4]

            track.confidence = detection[5]

            track.lost = 0

            # Refresh template using the newly detected box.
            template = (
                track.create_template(
                    frame
                )
            )

            if template is not None:

                track.template = (
                    template
                )

            matched.add(
                best_index
            )

        else:

            tracks.append(
                NumberTrack(
                    frame,
                    detection
                )
            )

    for index, track in enumerate(
        tracks
    ):

        if index not in matched:

            track.lost += 1

def redact(
    frame,
    track
):

    height, width = (
        frame.shape[:2]
    )

    x1 = max(
        0,
        int(track.x) -
        PADDING_X
    )

    y1 = max(
        0,
        int(track.y) -
        PADDING_Y
    )

    x2 = min(
        width,
        int(
            track.x +
            track.w +
            PADDING_X
        )
    )

    y2 = min(
        height,
        int(
            track.y +
            track.h +
            PADDING_Y
        )
    )

    if (
        x2 <= x1
        or
        y2 <= y1
    ):

        return

    frame[
        y1:y2,
        x1:x2
    ] = REDACTION_COLOR

def create_writer(
    output_path,
    fps,
    width,
    height
):

    fourcc = 0x7634706D

    writer = cv2.VideoWriter(
        output_path,
        fourcc,
        fps,
        (
            width,
            height
        )
    )

    if not writer.isOpened():

        raise RuntimeError(
            f"Could not create output:\n"
            f"{output_path}"
        )

    return writer

def process_chunk(
    cap,
    output_path,
    start_frame,
    end_frame,
    fps,
    width,
    height
):

    tracks = []


    cap.set(
        cv2.CAP_PROP_POS_FRAMES,
        start_frame
    )

    writer = create_writer(
        output_path,
        fps,
        width,
        height
    )

    total_frames = (
        end_frame -
        start_frame
    )

    processed = 0

    ocr_count = 0

    start_time = time.time()

    while (
        processed <
        total_frames
    ):

        ret, frame = cap.read()

        if not ret:

            break

        processed += 1

        for track in tracks:

            track.update(
                frame
            )

        should_run_ocr = (
            processed == 1
            or
            processed %
            OCR_INTERVAL == 0
        )

        if should_run_ocr:

            ocr_count += 1

            detections = (
                detect_numbers(
                    frame
                )
            )

            update_tracks(
                tracks,
                detections,
                frame
            )


        tracks = [
            track
            for track in tracks
            if track.lost
            <=
            MAX_LOST_FRAMES
        ]

        for track in tracks:

            redact(
                frame,
                track
            )

        writer.write(
            frame
        )

        if (
            processed % 10 == 0
            or
            processed == total_frames
        ):

            elapsed = (
                time.time()
                -
                start_time
            )

            speed = (
                processed /
                elapsed
                if elapsed > 0
                else 0
            )

            percent = (
                processed /
                total_frames *
                100
            )

            print(
                f"\r"
                f"Progress: "
                f"{percent:6.1f}% | "
                f"Speed: "
                f"{speed:6.1f} FPS | "
                f"OCR: "
                f"{ocr_count} | "
                f"Tracks: "
                f"{len(tracks)}",
                end="",
                flush=True
            )

    print()

    writer.release()

    elapsed = (
        time.time()
        -
        start_time
    )

    return (
        processed,
        elapsed,
        ocr_count
    )

def main():

    if not os.path.exists(
        INPUT_VIDEO
    ):

        raise FileNotFoundError(
            f"Input video not found:\n"
            f"{INPUT_VIDEO}"
        )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    cap = cv2.VideoCapture(
        INPUT_VIDEO
    )

    if not cap.isOpened():

        raise RuntimeError(
            f"Could not open:\n"
            f"{INPUT_VIDEO}"
        )

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    frame_count = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    if fps <= 0:

        cap.release()

        raise RuntimeError(
            "Could not determine FPS."
        )

    duration = (
        frame_count /
        fps
    )

    print()
    print("=" * 70)
    print("RAPIDOCR CONFIDENTIAL NUMBER REDACTION")
    print("=" * 70)

    print(
        f"Input video : {INPUT_VIDEO}"
    )

    print(
        f"Resolution  : "
        f"{width} x {height}"
    )

    print(
        f"FPS         : "
        f"{fps:.2f}"
    )

    print(
        f"Frames      : "
        f"{frame_count}"
    )

    print(
        f"Duration    : "
        f"{duration:.2f} seconds"
    )

    print()

    number_of_chunks = max(
        1,
        math.ceil(
            duration /
            MAX_VIDEO_DURATION
        )
    )

    if duration > MAX_VIDEO_DURATION:

        print(
            f"⚠ Video is longer than "
            f"{MAX_VIDEO_DURATION:.0f} seconds."
        )

        print(
            f"It will be split into "
            f"{number_of_chunks} parts."
        )

        print()

    else:

        print(
            "✓ Video is within the "
            f"{MAX_VIDEO_DURATION:.0f}-second limit."
        )

        print()

    overall_start = time.time()

    output_files = []

    for chunk_number in range(
        number_of_chunks
    ):

        start_seconds = (
            chunk_number *
            MAX_VIDEO_DURATION
        )

        end_seconds = min(
            duration,
            (
                chunk_number + 1
            ) *
            MAX_VIDEO_DURATION
        )

        start_frame = int(
            round(
                start_seconds *
                fps
            )
        )

        end_frame = min(
            frame_count,
            int(
                round(
                    end_seconds *
                    fps
                )
            )
        )

        if number_of_chunks == 1:

            filename = (
                "redacted_no_audio2.mp4"
            )

        else:

            filename = (
                f"redacted_part_"
                f"{chunk_number + 1:03d}.mp4"
            )

        output_path = os.path.join(
            OUTPUT_DIR,
            filename
        )

        output_files.append(
            output_path
        )

        print()
        print("-" * 70)

        print(
            f"PART "
            f"{chunk_number + 1}/"
            f"{number_of_chunks}"
        )

        print(
            f"Time: "
            f"{start_seconds:.2f}s → "
            f"{end_seconds:.2f}s"
        )

        print(
            f"Output: "
            f"{output_path}"
        )

        print("-" * 70)

        processed, elapsed, ocr_count = (
            process_chunk(
                cap,
                output_path,
                start_frame,
                end_frame,
                fps,
                width,
                height
            )
        )

        if elapsed > 0:

            speed = (
                processed /
                elapsed
            )

        else:

            speed = 0

        print(
            f"✓ Part "
            f"{chunk_number + 1} complete."
        )

        print(
            f"  Frames processed: "
            f"{processed}"
        )

        print(
            f"  OCR scans: "
            f"{ocr_count}"
        )

        print(
            f"  Processing speed: "
            f"{speed:.1f} FPS"
        )

    cap.release()

    cv2.destroyAllWindows()

    total_elapsed = (
        time.time()
        -
        overall_start
    )

    print()
    print()
    print("=" * 70)
    print("REDACTION COMPLETE")
    print("=" * 70)

    print(
        f"Total processing time: "
        f"{total_elapsed:.1f} seconds"
    )

    print()

    print(
        "Output files:"
    )

    for output_file in output_files:

        print(
            f"  {output_file}"
        )

    print()

    print(
        "Audio: NONE"
    )

    print("=" * 70)

if __name__ == "__main__":

    main()