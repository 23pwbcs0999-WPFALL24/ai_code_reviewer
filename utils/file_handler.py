"""
utils/file_handler.py
─────────────────────
Handles all file I/O concerns:
  - Detecting programming language from file extension
  - Reading uploaded single files
  - Extracting and combining code from uploaded ZIP archives
  - Enforcing file size limits
"""

import io
import os
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from config.settings import settings


# ─── Language Detection ───────────────────────────────────────────────────────

def detect_language(filename: str) -> Optional[str]:
    """
    Returns the language display name for a given filename, or None if
    the extension is not in our supported list.

    Example:
        detect_language("main.py")  → "Python"
        detect_language("app.rb")   → None
    """
    ext = Path(filename).suffix.lower()
    return settings.SUPPORTED_LANGUAGES.get(ext)


def is_supported_file(filename: str) -> bool:
    """True if we can review this file type."""
    return detect_language(filename) is not None


# ─── Single File Reader ───────────────────────────────────────────────────────

def read_uploaded_file(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """
    Decode raw bytes from an uploaded file into a string.

    Returns:
        (code_string, language_name)

    Raises:
        ValueError: if file is too large, unsupported, or not valid UTF-8
    """
    # Check size
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise ValueError(
            f"File is {size_mb:.1f} MB — maximum allowed is "
            f"{settings.MAX_FILE_SIZE_MB} MB."
        )

    # Check language support
    language = detect_language(filename)
    if language is None:
        supported = ", ".join(settings.SUPPORTED_LANGUAGES.keys())
        raise ValueError(
            f"'{filename}' is not a supported file type. "
            f"Supported extensions: {supported}"
        )

    # Decode
    try:
        code = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            "Could not read the file — it may not be a plain text file."
        )

    # Check line count
    lines = code.splitlines()
    if len(lines) > settings.MAX_CODE_LINES:
        raise ValueError(
            f"File has {len(lines)} lines — maximum allowed is "
            f"{settings.MAX_CODE_LINES}. "
            "Please split large files or review in smaller chunks."
        )

    return code, language


# ─── ZIP Archive Reader ───────────────────────────────────────────────────────

def read_zip_archive(zip_bytes: bytes) -> Tuple[str, str, list]:
    """
    Extract all supported source files from a ZIP archive and concatenate
    them into a single reviewable string with file separators.

    Returns:
        (combined_code, language_name, list_of_filenames_included)

    Raises:
        ValueError: if ZIP is invalid, too large, or has no supported files
    """
    total_size_mb = len(zip_bytes) / (1024 * 1024)
    if total_size_mb > settings.MAX_FILE_SIZE_MB * 3:   # ZIP limit is 3× single-file
        raise ValueError(
            f"ZIP archive is {total_size_mb:.1f} MB — maximum allowed is "
            f"{settings.MAX_FILE_SIZE_MB * 3} MB."
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise ValueError("The uploaded file is not a valid ZIP archive.")

    combined_parts: list[str] = []
    included_files: list[str] = []
    total_lines = 0

    for entry in sorted(zf.namelist()):
        # Skip directories, hidden files, __pycache__, etc.
        if _should_skip(entry):
            continue

        if not is_supported_file(entry):
            continue

        try:
            raw = zf.read(entry)
            code = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue

        lines = code.splitlines()
        total_lines += len(lines)

        if total_lines > settings.MAX_CODE_LINES:
            # Stop adding files once we hit the line limit
            break

        # Add a clear file separator so the LLM knows which file it's in
        header = f"# {'='*70}\n# FILE: {entry}\n# {'='*70}\n"
        combined_parts.append(header + code)
        included_files.append(entry)

    if not combined_parts:
        supported = ", ".join(settings.SUPPORTED_LANGUAGES.keys())
        raise ValueError(
            f"No supported files found in the ZIP. "
            f"Supported file types: {supported}"
        )

    combined_code = "\n\n".join(combined_parts)
    # Infer language from the first file found
    language = detect_language(included_files[0]) or "Python"
    return combined_code, language, included_files


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _should_skip(path: str) -> bool:
    """
    Returns True for paths we always want to ignore inside a ZIP:
    directories, __pycache__, hidden files, test fixtures, etc.
    """
    parts = Path(path).parts
    skip_dirs = {
        "__pycache__", ".git", ".venv", "venv", "node_modules",
        ".idea", ".vscode", "dist", "build", "eggs", ".eggs",
    }
    for part in parts:
        if part in skip_dirs or part.startswith("."):
            return True
    # Skip empty directory entries
    return path.endswith("/")


def count_lines(code: str) -> int:
    """Simple line counter (ignores blank-only trailing newline)."""
    return len(code.rstrip("\n").splitlines())
