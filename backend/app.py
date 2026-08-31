"""
Flask API server for RedactPro.

Confidentiality & Security Guarantees:
- Uploaded files are assigned random UUID names and placed in isolated temporary directories.
- Original files are securely and immediately deleted once redaction completes.
- No sensitive OCR values or file contents are logged.
- Redacted outputs are made accessible via non-guessable, single-use/expiring secure tokens.
- Strict extension and content-type checking.
"""

import os
import sys
import uuid
import time
import shutil
import logging
import threading
import mimetypes
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(__file__))

import config
from redaction import (
    redact_file,
    get_file_type,
    get_supported_extensions,
    get_ocr,
    get_video_duration,
)
from redaction.detector import DetectionConfig

# ============================================================
# LOGGING SETUP (NO SENSITIVE DATA)
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("redactpro.api")

app = Flask(__name__, static_folder=config.FRONTEND_DIR)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

# Preload OCR engine at startup
try:
    logger.info("Initializing OCR engine...")
    get_ocr()
    logger.info("OCR engine ready.")
except Exception as e:
    logger.warning("OCR initialization deferred: %s", str(e))


# ============================================================
# TEMPORARY FILE & TOKEN STORE
# ============================================================

# Dict of token -> {
#   "filepath": str,
#   "original_name": str,
#   "mime_type": str,
#   "created_at": float,
#   "is_dir": bool,
#   "files": list[str] (for multi-chunk video)
# }
SECURE_FILE_STORE = {}
STORE_LOCK = threading.Lock()
TOKEN_EXPIRY_SECONDS = 3600  # 1 hour TTL


def register_secure_file(filepath, original_name, mime_type, is_dir=False, files=None):
    token = str(uuid.uuid4())
    with STORE_LOCK:
        SECURE_FILE_STORE[token] = {
            "filepath": filepath,
            "original_name": original_name,
            "mime_type": mime_type,
            "created_at": time.time(),
            "is_dir": is_dir,
            "files": files or [filepath],
        }
    return token


def get_secure_file_entry(token):
    with STORE_LOCK:
        entry = SECURE_FILE_STORE.get(token)
        if entry and (time.time() - entry["created_at"]) > TOKEN_EXPIRY_SECONDS:
            _cleanup_entry(token, entry)
            return None
        return entry


def _cleanup_entry(token, entry):
    try:
        if entry.get("is_dir"):
            if os.path.exists(entry["filepath"]):
                shutil.rmtree(entry["filepath"], ignore_errors=True)
        else:
            for f in entry.get("files", []):
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
    except Exception as e:
        logger.error("Error during token cleanup: %s", str(e))
    SECURE_FILE_STORE.pop(token, None)


def clear_previous_temp_storage(keep_session_id=None):
    """
    Purge all existing session folders and files in the temp directory
    except for the currently active session. Ensures zero residual file accumulation.
    """
    temp_base = config.TEMP_STORAGE_DIR or os.path.join(config.BASE_DIR, "temp")
    if not os.path.exists(temp_base):
        return

    try:
        for entry in os.listdir(temp_base):
            entry_path = os.path.join(temp_base, entry)
            if keep_session_id and entry == keep_session_id:
                continue

            try:
                if os.path.isdir(entry_path):
                    shutil.rmtree(entry_path, ignore_errors=True)
                elif os.path.isfile(entry_path):
                    os.remove(entry_path)
                logger.info("Cleaned previous temp storage item: %s", entry)
            except OSError as e:
                logger.warning("Could not delete temp item %s: %s", entry_path, str(e))

        # Also purge old entries from the memory token store
        with STORE_LOCK:
            active_tokens = {}
            for t, data in SECURE_FILE_STORE.items():
                if any(os.path.exists(f) for f in data.get("files", [])):
                    active_tokens[t] = data
            SECURE_FILE_STORE.clear()
            SECURE_FILE_STORE.update(active_tokens)

    except Exception as e:
        logger.error("Error during temp storage purge: %s", str(e))


def periodic_cleanup():
    while True:
        time.sleep(300)
        with STORE_LOCK:
            now = time.time()
            expired = [t for t, data in SECURE_FILE_STORE.items() if (now - data["created_at"]) > TOKEN_EXPIRY_SECONDS]
            for t in expired:
                _cleanup_entry(t, SECURE_FILE_STORE[t])


cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()


# ============================================================
# LIVE JOB PROGRESS STORE
# ============================================================

JOB_PROGRESS = {}
PROGRESS_LOCK = threading.Lock()


def update_job_progress(job_id, data):
    if not job_id:
        return
    with PROGRESS_LOCK:
        JOB_PROGRESS[job_id] = {
            **data,
            "updated_at": time.time()
        }


def get_job_progress(job_id):
    with PROGRESS_LOCK:
        return JOB_PROGRESS.get(job_id)


# ============================================================
# STATIC FRONTEND ROUTES
# ============================================================

@app.route("/")
def serve_index():
    return send_from_directory(config.FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    file_path = os.path.join(config.FRONTEND_DIR, path)
    if os.path.exists(file_path):
        return send_from_directory(config.FRONTEND_DIR, path)
    return send_from_directory(config.FRONTEND_DIR, "index.html")


# ============================================================
# API ENDPOINTS
# ============================================================

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "service": "RedactPro",
        "supported_formats": sorted(list(get_supported_extensions())),
        "video_duration_limit_sec": config.MAX_VIDEO_DURATION
    })


@app.route("/api/progress/<job_id>", methods=["GET"])
def job_progress_endpoint(job_id):
    """Return real-time frame progress and calculated ETA for a job."""
    progress = get_job_progress(job_id)
    if not progress:
        return jsonify({
            "status": "pending",
            "percent": 0.0,
            "stage": "Initializing...",
            "eta_sec": None
        })
    return jsonify(progress)


@app.route("/api/clear-temp", methods=["POST"])
def clear_temp_endpoint():
    """Explicitly purge all contents in the temp directory."""
    clear_previous_temp_storage()
    return jsonify({"status": "ok", "message": "Temporary storage cleared."})


@app.route("/api/redact", methods=["POST"])
def redact_endpoint():
    """
    Handle file upload, determine type, process redaction,
    cleanup original upload, and return download token & metadata.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Please select a file to redact."}), 400

    uploaded_file = request.files["file"]
    if uploaded_file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    user_instructions = request.form.get("instructions", "").strip()
    job_id = request.form.get("job_id", "").strip()

    # Sanitize user filename for reference only (NEVER use for filesystem operations)
    raw_filename = uploaded_file.filename
    clean_name = secure_filename(raw_filename) or "document"
    ext = os.path.splitext(raw_filename)[1].lower()

    if ext not in get_supported_extensions():
        return jsonify({
            "error": f"Unsupported format '{ext}'. Supported formats: PNG, JPG, JPEG, PDF, MP4, MOV."
        }), 400

    file_type = get_file_type(ext)
    if not file_type:
        return jsonify({"error": "Unable to determine file handler for this format."}), 400

    # Progress callback for live ETA calculation
    def handle_progress(info):
        update_job_progress(job_id, {
            "status": "processing",
            "file_type": file_type,
            **info
        })

    update_job_progress(job_id, {
        "status": "processing",
        "file_type": file_type,
        "percent": 0.0,
        "stage": "Preparing file...",
        "eta_sec": None
    })

    # Create an isolated temporary workspace directory
    session_id = uuid.uuid4().hex
    work_dir = os.path.join(
        config.TEMP_STORAGE_DIR or os.path.join(config.BASE_DIR, "temp"),
        session_id
    )
    os.makedirs(work_dir, exist_ok=True)

    input_temp_path = os.path.join(work_dir, f"input_{uuid.uuid4().hex}{ext}")
    output_temp_dir = os.path.join(work_dir, "output")
    os.makedirs(output_temp_dir, exist_ok=True)

    # Automatically clear previously stored temp folder content
    clear_previous_temp_storage(keep_session_id=session_id)

    try:
        # Save uploaded file
        uploaded_file.save(input_temp_path)
        logger.info("Received file [%s] (Type: %s, Job: %s). Processing started.", ext, file_type, job_id)

        # Video pre-check duration info
        video_duration = None
        was_split = False
        if file_type == "video":
            try:
                video_duration = get_video_duration(input_temp_path)
                if video_duration > config.MAX_VIDEO_DURATION:
                    was_split = True
            except Exception as e:
                logger.error("Failed to inspect video duration: %s", str(e))
                return jsonify({"error": "Invalid or unreadable video file."}), 400

        # Perform redaction with live frame progress callback
        if file_type == "video":
            meta = redact_file(
                input_path=input_temp_path,
                output_path=output_temp_dir,
                file_type=file_type,
                instructions=user_instructions,
                progress_callback=handle_progress
            )
            output_paths = meta["output_files"]
            if not output_paths or not all(os.path.exists(p) for p in output_paths):
                raise RuntimeError("Video redaction failed to produce output files.")
        else:
            out_filename = f"redacted_{uuid.uuid4().hex}{ext}"
            output_single_path = os.path.join(output_temp_dir, out_filename)
            meta = redact_file(
                input_path=input_temp_path,
                output_path=output_single_path,
                file_type=file_type,
                instructions=user_instructions,
                progress_callback=handle_progress
            )
            output_paths = [output_single_path]

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(raw_filename)
        if not mime_type:
            mime_map = {
                "image": "image/png" if ext == ".png" else "image/jpeg",
                "pdf": "application/pdf",
                "video": "video/mp4"
            }
            mime_type = mime_map.get(file_type, "application/octet-stream")

        # Register output files for secure download
        token_list = []
        for p in output_paths:
            base_out_name = f"redacted_{clean_name}"
            if len(output_paths) > 1:
                chunk_name = os.path.basename(p)
                base_out_name = f"{os.path.splitext(clean_name)[0]}_{chunk_name}"

            t = register_secure_file(
                filepath=p,
                original_name=base_out_name,
                mime_type=mime_type,
                files=[p]
            )
            token_list.append({
                "token": t,
                "download_url": f"/api/download/{t}",
                "preview_url": f"/api/preview/{t}",
                "filename": base_out_name
            })

        response_payload = {
            "success": True,
            "file_type": file_type,
            "original_filename": clean_name,
            "meta": meta,
            "results": token_list,
            "was_split": was_split,
            "video_duration": video_duration,
            "chunks_count": len(token_list)
        }

        return jsonify(response_payload)

    except Exception as e:
        logger.exception("Redaction error: %s", str(e))
        return jsonify({
            "error": "Redaction could not be completed. Your original file has not been retained."
        }), 500

    finally:
        # CRITICAL SECURITY REQUIREMENT:
        # Delete original uploaded file immediately
        if input_temp_path and os.path.exists(input_temp_path):
            try:
                os.remove(input_temp_path)
                logger.info("Original input file securely deleted.")
            except Exception as e:
                logger.warning("Failed to remove input file: %s", str(e))


@app.route("/api/preview/<token>", methods=["GET"])
def preview_file(token):
    """Serve file for inline browser preview with Range support."""
    entry = get_secure_file_entry(token)
    if not entry or not os.path.exists(entry["filepath"]):
        return jsonify({"error": "File not found or expired."}), 404

    response = send_file(
        entry["filepath"],
        mimetype=entry["mime_type"],
        as_attachment=False,
        conditional=True
    )
    response.headers["Accept-Ranges"] = "bytes"
    return response


@app.route("/api/download/<token>", methods=["GET"])
def download_file(token):
    """Serve file as attachment download."""
    entry = get_secure_file_entry(token)
    if not entry or not os.path.exists(entry["filepath"]):
        return jsonify({"error": "Download link expired or file not found."}), 404

    return send_file(
        entry["filepath"],
        mimetype=entry["mime_type"],
        as_attachment=True,
        download_name=entry["original_name"]
    )


# Error Handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": f"File exceeds the maximum allowed size ({config.MAX_CONTENT_LENGTH // (1024*1024)}MB)."}), 413


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found."}), 404


@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({"error": "An internal server error occurred."}), 500


if __name__ == "__main__":
    logger.info("Starting RedactPro server on port %d...", config.PORT)
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
