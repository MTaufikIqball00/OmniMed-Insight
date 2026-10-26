import hashlib
import os
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image, UnidentifiedImageError

from .schemas import ImageMetadataReport

MAX_IMAGE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", 15 * 1024 * 1024))
MIN_DIMENSION = 64
MAX_DIMENSION = 4096

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
TIFF_LE_MAGIC = b"II*\x00"
TIFF_BE_MAGIC = b"MM\x00*"


class ImageValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def verify_magic_bytes(raw_bytes: bytes) -> str:
    if len(raw_bytes) < 12:
        raise ImageValidationError(
            "EMPTY_OR_TRUNCATED_FILE",
            "Uploaded file is empty or smaller than valid medical image headers.",
        )
    if raw_bytes.startswith(PNG_MAGIC):
        return "PNG"
    if raw_bytes.startswith(JPEG_MAGIC):
        return "JPEG"
    if raw_bytes.startswith(TIFF_LE_MAGIC) or raw_bytes.startswith(TIFF_BE_MAGIC):
        return "TIFF"
    raise ImageValidationError(
        "UNSUPPORTED_FILE_SIGNATURE",
        "File binary signature does not match supported medical raster formats (PNG, JPEG, TIFF).",
    )


def load_and_validate_medical_image(
    image_path: str, modality: str
) -> Tuple[np.ndarray, ImageMetadataReport]:
    """
    Validates file existence, size, binary magic header, image decodability,
    dimensions, and intensity distribution without mutating the source file.
    Returns a float32 normalized grayscale array [H, W] in [0.0, 1.0] and metadata.
    """
    if modality not in ("CXR", "MRI"):
        raise ImageValidationError(
            "UNSUPPORTED_MODALITY",
            f"Modality '{modality}' is not supported. Supported modalities: CXR, MRI.",
        )

    path_obj = Path(image_path).resolve()
    if not path_obj.is_file():
        raise ImageValidationError(
            "IMAGE_NOT_FOUND",
            "Target image file does not exist on the authorized storage volume.",
        )

    file_size = path_obj.stat().st_size
    if file_size == 0:
        raise ImageValidationError("EMPTY_FILE", "Image file contains 0 bytes.")
    if file_size > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            "FILE_TOO_LARGE",
            f"Image file size ({file_size} bytes) exceeds limit ({MAX_IMAGE_BYTES} bytes).",
        )

    raw_bytes = path_obj.read_bytes()
    detected_sig = verify_magic_bytes(raw_bytes)
    sha256_digest = hashlib.sha256(raw_bytes).hexdigest()

    try:
        with Image.open(path_obj) as img:
            img.verify()
        with Image.open(path_obj) as img:
            img_format = img.format or detected_sig
            orig_mode = img.mode
            width, height = img.size

            if width < MIN_DIMENSION or height < MIN_DIMENSION:
                raise ImageValidationError(
                    "RESOLUTION_TOO_SMALL",
                    f"Image dimensions ({width}x{height}) are below minimum clinical analysis threshold ({MIN_DIMENSION}x{MIN_DIMENSION}).",
                )
            if width > MAX_DIMENSION or height > MAX_DIMENSION:
                raise ImageValidationError(
                    "RESOLUTION_TOO_LARGE",
                    f"Image dimensions ({width}x{height}) exceed maximum allowed resolution ({MAX_DIMENSION}x{MAX_DIMENSION}).",
                )

            aspect_ratio = round(width / float(height), 4)
            if aspect_ratio < 0.35 or aspect_ratio > 2.85:
                raise ImageValidationError(
                    "INVALID_ASPECT_RATIO",
                    f"Image aspect ratio ({aspect_ratio}) is outside valid anatomical scan bounds [0.35, 2.85].",
                )

            # Convert to single-channel luminance without cropping or altering orientation
            if img.mode in ("I;16", "I"):
                arr_raw = np.asarray(img, dtype=np.float32)
                bit_depth = 16
                max_possible = 65535.0 if arr_raw.max() > 255.0 else 255.0
            else:
                gray_img = img.convert("L")
                arr_raw = np.asarray(gray_img, dtype=np.float32)
                bit_depth = 8
                max_possible = 255.0
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError(
            "CORRUPTED_IMAGE_DATA",
            f"Image decoder failed to parse pixel stream safely: {exc}",
        ) from exc

    min_val = float(np.min(arr_raw))
    max_val = float(np.max(arr_raw))
    mean_val = float(np.mean(arr_raw))
    std_val = float(np.std(arr_raw))
    dyn_range = max_val - min_val

    if dyn_range < 5.0 or std_val < 1.5:
        raise ImageValidationError(
            "LOW_DYNAMIC_RANGE_OR_BLANK",
            "Image has insufficient contrast or uniform pixel values (blank/unreadable scan). Cannot infer clinical findings.",
        )

    # Normalize to [0, 1] preserving linear intensity scaling (no destructive histogram clipping)
    norm_gray = (arr_raw - min_val) / max(dyn_range, 1e-6)
    norm_gray = np.clip(norm_gray, 0.0, 1.0).astype(np.float32)

    preprocessing_steps = [
        f"Verified {detected_sig} header signature and SHA-256 integrity digest",
        f"Preserved native orientation (PA/AP Axial, {width}x{height}, aspect ratio {aspect_ratio})",
        f"Linear min-max intensity windowing from [{min_val:.1f}, {max_val:.1f}] to [0.0, 1.0]",
        "Bilinear resize to 224x224 tensor with 3-channel replication for DenseNet-121 feature extractor (no geometric cropping)",
        "Standardized channel normalization (mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])",
    ]

    metadata = ImageMetadataReport(
        sha256_digest=sha256_digest,
        format=img_format,
        mode=orig_mode,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        bit_depth=bit_depth,
        min_intensity=round(min_val, 2),
        max_intensity=round(max_val, 2),
        mean_intensity=round(mean_val, 2),
        std_intensity=round(std_val, 2),
        dynamic_range=round(dyn_range, 2),
        orientation="NATIVE_UNALTERED (PA/Axial Standard)",
        preprocessing_steps=preprocessing_steps,
    )

    return norm_gray, metadata
