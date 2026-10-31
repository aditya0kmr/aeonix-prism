"""
ÆONIX PRISM // VISIA Visual Intelligence & Forensic Image Engine
Document OCR, forensic EXIF metadata extraction, cryptographic integrity, and VERITAS case linkage.
Zero Paid APIs, 100% Offline Local Provenance.
"""

import os
import json
import time
import hashlib
import subprocess
import tempfile
from typing import Dict, Any, Optional

from PIL import Image, ExifTags
from aeonix.core.db import log_audit_event
from aeonix.core.veritas import ingest_evidence

def compute_sha256(file_path: str) -> str:
    """Computes SHA-256 checksum of an image file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def extract_exif_metadata(image_path: str) -> Dict[str, Any]:
    """Extracts forensic EXIF tags and GPS telemetry from an image."""
    exif_data = {}
    try:
        with Image.open(image_path) as img:
            raw_exif = img._getexif()
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    # Handle bytes and non-serializable objects
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8", errors="replace")
                        except Exception:
                            value = str(value)
                    elif isinstance(value, tuple) or isinstance(value, list):
                        value = [str(x) for x in value]
                    elif not isinstance(value, (str, int, float, bool, dict)):
                        value = str(value)
                    exif_data[tag_name] = value
    except Exception as e:
        exif_data["exif_error"] = str(e)

    return exif_data

def extract_ocr_text(image_path: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Extracts text from document or screenshot using native Tesseract engine."""
    try:
        out = subprocess.check_output(
            ["tesseract", image_path, "stdout", "-l", "eng", "--oem", "1", "--psm", "3"],
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            text=True
        )
        text = out.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return {
            "success": True,
            "text": text,
            "line_count": len(lines),
            "word_count": len(text.split()),
            "character_count": len(text)
        }
    except Exception as e:
        return {
            "success": False,
            "text": "",
            "error": str(e)
        }

def analyze_visual_artifact(
    file_path: str, 
    case_id: Optional[str] = None, 
    run_ocr: bool = True,
    actor: str = "Aadi"
) -> Dict[str, Any]:
    """
    Performs comprehensive visual forensic analysis:
    - Geometry and image dimensions
    - SHA-256 cryptographic digest
    - Forensic EXIF metadata
    - Offline OCR text extraction
    - Optional automated preservation into VERITAS evidence vault
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Visual artifact not found: {file_path}")

    t0 = time.perf_counter()
    sha256 = compute_sha256(file_path)
    file_size = os.path.getsize(file_path)

    # Image properties
    with Image.open(file_path) as img:
        width, height = img.size
        img_format = img.format or "UNKNOWN"
        img_mode = img.mode

    # EXIF tags
    exif = extract_exif_metadata(file_path)

    # Document OCR
    ocr_result = extract_ocr_text(file_path) if run_ocr else {"success": False, "skipped": True}

    veritas_evidence = None
    if case_id:
        try:
            veritas_evidence = ingest_evidence(
                case_id=case_id,
                source_file=file_path,
                mime_type=f"image/{img_format.lower()}",
                metadata={
                    "width": width,
                    "height": height,
                    "format": img_format,
                    "has_exif": bool(exif),
                    "ocr_word_count": ocr_result.get("word_count", 0)
                },
                collected_by=actor
            )
        except Exception as e:
            veritas_evidence = {"error": str(e)}

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    log_audit_event(
        actor=actor,
        action="visia_artifact_analyzed",
        target=file_path,
        result="success",
        details={
            "sha256": sha256,
            "dimensions": f"{width}x{height}",
            "format": img_format,
            "ocr_words": ocr_result.get("word_count", 0),
            "case_id": case_id,
            "latency_ms": latency_ms
        }
    )

    return {
        "success": True,
        "file_name": os.path.basename(file_path),
        "sha256": sha256,
        "size_bytes": file_size,
        "dimensions": {"width": width, "height": height, "aspect_ratio": round(width / max(height, 1), 2)},
        "format": img_format,
        "mode": img_mode,
        "exif": exif,
        "ocr": ocr_result,
        "case_link": veritas_evidence,
        "latency_ms": latency_ms
    }
