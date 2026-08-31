"""
Video redaction module for RedactPro.

Handles MP4 and MOV files.
Refactored from the original blur_numbers_vid.py script.

Pipeline:
  1. Open video, validate duration (10s limit)
  2. Split into 10-second chunks if necessary
  3. For each chunk:
     a. Process frames sequentially
     b. Run OCR periodically (every N frames)
     c. Track detected regions between OCR scans via template matching
     d. Apply solid black redaction boxes to every frame
     e. Write redacted frames to output video
  4. No audio in initial version

The tracking system prevents "blinking" redactions by maintaining
detected regions between OCR scans using OpenCV template matching.
"""

import cv2
import numpy as np
import os
import time
import math
import logging

from .detector import (
    detect_sensitive_regions,
    apply_redactions,
    DetectionConfig,
)
from .utils import calculate_iou, center_distance


logger = logging.getLogger("redactpro.video")


# ============================================================
# VIDEO-SPECIFIC CONFIGURATION
# ============================================================

# Maximum video duration in seconds
MAX_VIDEO_DURATION = 10.0

# Run OCR every N frames (balance speed vs accuracy)
OCR_INTERVAL = 3

# Template matching search margin (pixels around last known position)
TRACK_SEARCH_MARGIN = 100

# Minimum template match confidence to keep tracking
TRACK_THRESHOLD = 0.55

# Frames a track can be "lost" before removal
MAX_LOST_FRAMES = 6

# Solid black
REDACTION_COLOR = (0, 0, 0)

# Padding for redaction boxes
PADDING_X = 2
PADDING_Y = 1


# ============================================================
# NUMBER TRACKER
# ============================================================

class NumberTrack:
    """
    Tracks a detected number region across video frames
    using OpenCV template matching.

    This prevents redaction boxes from blinking on/off
    between OCR scans.
    """

    def __init__(self, frame, detection):
        self.x = float(detection[0])
        self.y = float(detection[1])
        self.w = float(detection[2])
        self.h = float(detection[3])
        self.text = detection[4]
        self.confidence = detection[5]
        self.lost = 0
        self.template = self._create_template(frame)

    def _create_template(self, frame):
        """Extract grayscale template from current position."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        fh, fw = gray.shape

        x1 = max(0, int(self.x))
        y1 = max(0, int(self.y))
        x2 = min(fw, int(self.x + self.w))
        y2 = min(fh, int(self.y + self.h))

        if x2 <= x1 or y2 <= y1:
            return None

        template = gray[y1:y2, x1:x2]

        if template.size == 0:
            return None

        return template.copy()

    def update(self, frame):
        """
        Try to find this tracked region in the new frame
        using template matching.

        Returns True if the track was successfully updated.
        """
        if self.template is None:
            self.lost += 1
            return False

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        fh, fw = gray.shape

        old_x = int(self.x)
        old_y = int(self.y)

        # Search within a margin around last known position
        sx1 = max(0, old_x - TRACK_SEARCH_MARGIN)
        sy1 = max(0, old_y - TRACK_SEARCH_MARGIN)
        sx2 = min(fw, old_x + int(self.w) + TRACK_SEARCH_MARGIN)
        sy2 = min(fh, old_y + int(self.h) + TRACK_SEARCH_MARGIN)

        search = gray[sy1:sy2, sx1:sx2]

        th, tw = self.template.shape

        if search.shape[0] < th or search.shape[1] < tw:
            self.lost += 1
            return False

        result = cv2.matchTemplate(
            search,
            self.template,
            cv2.TM_CCOEFF_NORMED
        )

        _, confidence, _, location = cv2.minMaxLoc(result)

        if confidence < TRACK_THRESHOLD:
            self.lost += 1
            return False

        self.x = sx1 + location[0]
        self.y = sy1 + location[1]
        self.lost = 0

        return True

    def get_box(self):
        """Get current bounding box as [x, y, w, h, text, confidence]."""
        return [
            self.x, self.y, self.w, self.h,
            self.text, self.confidence
        ]


def _update_tracks(tracks, detections, frame):
    """
    Match new OCR detections to existing tracks.

    - Matched tracks get updated positions and refreshed templates
    - Unmatched detections become new tracks
    - Unmatched tracks increment their lost counter
    """
    matched = set()

    for detection in detections:
        best_index = None
        best_score = -1

        for index, track in enumerate(tracks):
            if index in matched:
                continue

            track_box = track.get_box()
            overlap = calculate_iou(detection, track_box)
            dist = center_distance(detection, track_box)

            if overlap > 0.10:
                score = overlap * 100
            elif dist < 100:
                score = 10 - (dist / 100)
            else:
                continue

            if score > best_score:
                best_score = score
                best_index = index

        if best_index is not None:
            track = tracks[best_index]
            track.x = detection[0]
            track.y = detection[1]
            track.w = detection[2]
            track.h = detection[3]
            track.text = detection[4]
            track.confidence = detection[5]
            track.lost = 0

            # Refresh template
            template = track._create_template(frame)
            if template is not None:
                track.template = template

            matched.add(best_index)
        else:
            tracks.append(NumberTrack(frame, detection))

    # Increment lost counter for unmatched tracks
    for index, track in enumerate(tracks):
        if index not in matched:
            track.lost += 1


def _redact_frame(frame, tracks):
    """Apply redaction boxes from all active tracks to a frame."""
    height, width = frame.shape[:2]

    for track in tracks:
        x1 = max(0, int(track.x) - PADDING_X)
        y1 = max(0, int(track.y) - PADDING_Y)
        x2 = min(width, int(track.x + track.w + PADDING_X))
        y2 = min(height, int(track.y + track.h + PADDING_Y))

        if x2 <= x1 or y2 <= y1:
            continue

        frame[y1:y2, x1:x2] = REDACTION_COLOR


def _convert_to_web_mp4(raw_mp4_path):
    """
    Convert raw OpenCV output to universal web-compatible H.264 (avc1/yuv420p/faststart).
    Ensures seamless HTML5 video preview in Chrome, Safari, Firefox.
    """
    import subprocess
    import shutil
    
    ffmpeg_bin = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not os.path.exists(ffmpeg_bin):
        logger.warning("ffmpeg not found at %s", ffmpeg_bin)
        return raw_mp4_path

    temp_web_path = raw_mp4_path + ".web.mp4"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", raw_mp4_path,
        "-c:v", "libx264",
        "-profile:v", "baseline",
        "-level", "3.0",
        "-preset", "veryfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        temp_web_path
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(temp_web_path) and os.path.getsize(temp_web_path) > 0:
            os.replace(temp_web_path, raw_mp4_path)
            logger.info("Successfully transcoded video to web H.264: %s (%d bytes)", raw_mp4_path, os.path.getsize(raw_mp4_path))
    except Exception as e:
        logger.warning("FFmpeg web transcode error: %s", str(e))
        if os.path.exists(temp_web_path):
            try:
                os.remove(temp_web_path)
            except OSError:
                pass

    return raw_mp4_path


def _create_writer(output_path, fps, width, height):
    """Create an MP4 video writer."""
    # mp4v codec
    fourcc = 0x7634706D

    writer = cv2.VideoWriter(
        output_path,
        fourcc,
        fps,
        (width, height)
    )

    if not writer.isOpened():
        raise RuntimeError(
            "Could not create video output file."
        )

    return writer


def _process_chunk(
    cap, output_path,
    start_frame, end_frame,
    fps, width, height,
    config,
    chunk_index=0,
    total_chunks=1,
    global_offset=0,
    total_video_frames=1,
    start_overall_time=None,
    progress_callback=None
):
    """
    Process a single chunk of video frames.

    Returns (frames_processed, detection_count).
    """
    tracks = []
    total_frames = end_frame - start_frame

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    writer = _create_writer(output_path, fps, width, height)

    processed = 0
    detection_count = 0
    chunk_start_time = time.time()
    if start_overall_time is None:
        start_overall_time = chunk_start_time

    try:
        while processed < total_frames:
            ret, frame = cap.read()
            if not ret:
                break

            processed += 1
            current_global = global_offset + processed

            # Update existing tracks via template matching
            for track in tracks:
                track.update(frame)

            # Run OCR periodically
            should_run_ocr = (
                processed == 1
                or processed % OCR_INTERVAL == 0
            )

            if should_run_ocr:
                detections = detect_sensitive_regions(frame, config)
                detection_count += len(detections)
                _update_tracks(tracks, detections, frame)

            # Remove lost tracks
            tracks = [
                t for t in tracks
                if t.lost <= MAX_LOST_FRAMES
            ]

            # Apply redactions
            _redact_frame(frame, tracks)

            writer.write(frame)

            # Calculate real-time frame processing speed and exact remaining time
            if progress_callback and (processed % 2 == 0 or processed == total_frames):
                elapsed = max(0.001, time.time() - start_overall_time)
                speed = current_global / elapsed
                remaining_frames = max(0, total_video_frames - current_global)
                eta_seconds = (remaining_frames / speed) if speed > 0 else 0.0
                percent = (current_global / max(1, total_video_frames)) * 100.0

                progress_callback({
                    "processed_frames": current_global,
                    "total_frames": total_video_frames,
                    "chunk": chunk_index + 1,
                    "total_chunks": total_chunks,
                    "percent": round(percent, 1),
                    "fps": round(speed, 1),
                    "elapsed_sec": round(elapsed, 1),
                    "eta_sec": round(eta_seconds, 1),
                    "stage": f"Part {chunk_index + 1}/{total_chunks}: Frame {current_global}/{total_video_frames}"
                })

    finally:
        writer.release()

    _convert_to_web_mp4(output_path)

    return processed, detection_count


# ============================================================
# PUBLIC API
# ============================================================

def get_video_duration(input_path: str) -> float:
    """Get video duration in seconds."""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError("Could not open video file.")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    if fps <= 0:
        raise RuntimeError("Could not determine video FPS.")

    return frame_count / fps


def redact_video(
    input_path: str,
    output_dir: str,
    config: DetectionConfig = None,
    progress_callback=None
) -> dict:
    """
    Redact sensitive information from a video file.

    Videos longer than MAX_VIDEO_DURATION are automatically split
    into chunks. Output is MP4 with no audio.

    Args:
        input_path: Path to the input video (MP4, MOV).
        output_dir: Directory to write output file(s).
        config: Detection configuration. Uses defaults if None.
        progress_callback: Optional callable receiving progress info dict.

    Returns:
        dict with processing metadata:
            - output_files: list of output file paths
            - duration: video duration in seconds
            - chunks: number of chunks processed
            - total_detections: total regions detected

    Raises:
        RuntimeError: If video cannot be opened or processed.
        ValueError: If video exceeds duration limit and splitting fails.
    """
    # --------------------------------------------------------
    # Open video
    # --------------------------------------------------------

    cap = cv2.VideoCapture(input_path)

    if not cap.isOpened():
        raise RuntimeError(
            "Could not open video file. "
            "The file may be corrupted or in an unsupported codec."
        )

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if fps <= 0:
        cap.release()
        raise RuntimeError("Could not determine video FPS.")

    duration = frame_count / fps

    logger.info(
        "Processing video: %dx%d, %.2f FPS, %.2fs duration (%d frames)",
        width, height, fps, duration, frame_count
    )

    # --------------------------------------------------------
    # Calculate chunks
    # --------------------------------------------------------

    num_chunks = max(1, math.ceil(duration / MAX_VIDEO_DURATION))

    if num_chunks > 1:
        logger.info(
            "Video exceeds %.0fs limit, splitting into %d chunks",
            MAX_VIDEO_DURATION, num_chunks
        )

    # --------------------------------------------------------
    # Process chunks
    # --------------------------------------------------------

    os.makedirs(output_dir, exist_ok=True)

    output_files = []
    total_detections = 0
    global_processed = 0
    overall_start_time = time.time()

    try:
        for chunk in range(num_chunks):
            start_seconds = chunk * MAX_VIDEO_DURATION
            end_seconds = min(duration, (chunk + 1) * MAX_VIDEO_DURATION)

            start_frame = int(round(start_seconds * fps))
            end_frame = min(frame_count, int(round(end_seconds * fps)))

            if num_chunks == 1:
                filename = "redacted_video.mp4"
            else:
                filename = f"redacted_part_{chunk + 1:03d}.mp4"

            output_path = os.path.join(output_dir, filename)
            output_files.append(output_path)

            logger.info(
                "Processing chunk %d/%d (%.1fs - %.1fs)",
                chunk + 1, num_chunks,
                start_seconds, end_seconds
            )

            processed, detections = _process_chunk(
                cap, output_path,
                start_frame, end_frame,
                fps, width, height,
                config,
                chunk_index=chunk,
                total_chunks=num_chunks,
                global_offset=global_processed,
                total_video_frames=frame_count,
                start_overall_time=overall_start_time,
                progress_callback=progress_callback
            )

            global_processed += processed
            total_detections += detections

            logger.info(
                "Chunk %d complete: %d frames, %d detections",
                chunk + 1, processed, detections
            )

    finally:
        cap.release()

    logger.info(
        "Video redaction complete: %d chunks, %d total detections",
        num_chunks, total_detections
    )

    return {
        "output_files": output_files,
        "duration": duration,
        "chunks": num_chunks,
        "total_detections": total_detections,
    }
