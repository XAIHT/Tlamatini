"""
screenshot.py - Capture the full screen and save as a .jpg file.

Logging strategy
----------------
* A module-level logger is created with the module's __name__.
* Two handlers are attached at runtime (only when run as __main__):
    - RotatingFileHandler  → screenshot.log  (all levels DEBUG+)
    - StreamHandler        → stdout          (INFO+ by default, DEBUG if --verbose)
* The root logger is NOT touched; library callers that import this module
  get only the module logger – they can attach their own handlers.
* Log format follows the recommended pattern:
    timestamp | level | logger | message   (+ exc_info on exceptions)

Requirements:
    pip install Pillow

    On Linux, also install one of:
        sudo apt install scrot           (X11)
        sudo apt install gnome-screenshot (Wayland/GNOME)
"""

import argparse
import datetime
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from PIL import ImageGrab

# ---------------------------------------------------------------------------
# Module-level logger – name follows the package hierarchy automatically.
# DO NOT add handlers here; that is the responsibility of the entry-point.
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging setup (called only by __main__)
# ---------------------------------------------------------------------------
LOG_FILE = "screenshot.log"
LOG_MAX_BYTES = 5 * 1920 * 1080   # 10 MB per file
LOG_BACKUP_COUNT = 3              # keep up to 3 rotated files

_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _configure_logging(verbose: bool = False) -> None:
    """
    Attach a RotatingFileHandler (DEBUG+) and a StreamHandler (INFO+ or DEBUG)
    to the root logger so that every logger in the application is covered.

    Using the root logger here is intentional for a standalone script; library
    code should use module-level loggers without configuring handlers.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)   # capture everything; handlers filter levels

    formatter = logging.Formatter(fmt=_FMT, datefmt=_DATE_FMT)

    # --- Rotating file handler (DEBUG and above) ----------------------------
    file_handler = logging.handlers.RotatingFileHandler(
        filename=LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # --- Console handler (INFO by default, DEBUG if --verbose) --------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logger.debug(
        "Logging initialised — file: '%s' (max %s MB x %d), "
        "console level: %s",
        LOG_FILE,
        LOG_MAX_BYTES // (1024 * 1024),
        LOG_BACKUP_COUNT,
        "DEBUG" if verbose else "INFO",
    )


# ---------------------------------------------------------------------------
# Core screenshot function
# ---------------------------------------------------------------------------

def take_screenshot(output_path: str = None, quality: int = 90) -> str:
    """
    Capture the full screen and save it as a JPEG file.

    Args:
        output_path: Destination file path.  Defaults to
                     ``screenshot_YYYYMMDD_HHMMSS.jpg`` in the CWD.
        quality:     JPEG compression quality 1-95 (default 90).

    Returns:
        Absolute path of the saved file.

    Raises:
        ValueError:      If *quality* is out of range.
        PermissionError: If the output directory is not writable.
        OSError:         If the file cannot be written.
        Exception:       Re-raised after logging for any unexpected error.
    """
    logger.info("Starting screenshot capture")
    logger.debug("Parameters — output_path=%r, quality=%d", output_path, quality)

    # --- Validate quality ---------------------------------------------------
    if not (1 <= quality <= 95):
        msg = f"quality must be between 1 and 95, got {quality}"
        logger.error("Invalid quality value: %d", quality)
        raise ValueError(msg)
    logger.debug("Quality value validated: %d", quality)

    # --- Build output path --------------------------------------------------
    if output_path is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"screenshot_{timestamp}.jpg"
        logger.debug("No output path supplied; using default: %s", output_path)
    else:
        logger.debug("Output path provided: %s", output_path)

    output_path = str(Path(output_path).resolve())
    logger.debug("Resolved absolute output path: %s", output_path)

    # --- Check target directory is writable ---------------------------------
    parent_dir = os.path.dirname(output_path)
    if not os.access(parent_dir, os.W_OK):
        msg = f"Output directory is not writable: {parent_dir}"
        logger.error(msg)
        raise PermissionError(msg)
    logger.debug("Output directory is writable: %s", parent_dir)

    # --- Capture the screen -------------------------------------------------
    logger.debug("Calling ImageGrab.grab() to capture full screen")
    try:
        screenshot = ImageGrab.grab()
    except Exception:
        logger.exception("Screen capture failed — ImageGrab.grab() raised an exception")
        raise

    width, height = screenshot.size
    logger.info("Screen captured successfully — resolution: %dx%d", width, height)

    # --- Convert colour mode ------------------------------------------------
    original_mode = screenshot.mode
    if original_mode != "RGB":
        logger.warning(
            "Unexpected image mode '%s'; converting to RGB for JPEG compatibility",
            original_mode,
        )
        screenshot = screenshot.convert("RGB")
        logger.debug("Image converted from %s to RGB", original_mode)
    else:
        logger.debug("Image mode is RGB — no conversion needed")

    # --- Save to disk -------------------------------------------------------
    logger.debug("Saving image to '%s' (JPEG quality=%d)", output_path, quality)
    try:
        screenshot.save(output_path, format="JPEG", quality=quality)
    except OSError:
        logger.exception("Failed to save screenshot to '%s'", output_path)
        raise

    file_size_kb = os.path.getsize(output_path) / 1024
    logger.info(
        "Screenshot saved -> %s (%.1f KB, quality=%d)",
        output_path,
        file_size_kb,
        quality,
    )

    logger.debug("take_screenshot() completed successfully")
    return output_path


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture the full screen and save it as a JPEG file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        metavar="FILE",
        help="Output file path (default: screenshot_<timestamp>.jpg)",
    )
    parser.add_argument(
        "-q", "--quality",
        type=int,
        default=90,
        metavar="1-95",
        help="JPEG quality (1-95)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Set console log level to DEBUG (file always captures DEBUG)",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()

    _configure_logging(verbose=args.verbose)

    logger.info("=== screenshot.py started ===")
    logger.debug(
        "CLI arguments — output=%r, quality=%d, verbose=%s",
        args.output,
        args.quality,
        args.verbose,
    )

    try:
        saved_path = take_screenshot(output_path=args.output, quality=args.quality)
        logger.info("All done. File: %s", saved_path)
    except ValueError as exc:
        logger.error("Argument error: %s", exc)
        sys.exit(2)
    except PermissionError as exc:
        logger.error("Permission denied: %s", exc)
        sys.exit(1)
    except Exception:
        logger.critical(
            "Unexpected error — screenshot was NOT saved", exc_info=True
        )
        sys.exit(1)
    finally:
        logger.info("=== screenshot.py finished ===")


if __name__ == "__main__":
    main()
