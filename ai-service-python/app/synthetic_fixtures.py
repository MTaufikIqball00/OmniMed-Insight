import hashlib
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw


def generate_synthetic_cxr(output_path: Path, focal_opacity: bool = True) -> Tuple[str, int, int]:
    """
    Generates a clearly labeled synthetic 512x512 PA Chest Radiograph phantom
    with thoracic cage ribs, cardiac silhouette, diaphragmatic domes, and an
    optional focal right-lower-zone parenchymal opacity for XAI testing.
    """
    w, h = 512, 512
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2.0) / (w / 2.0)
    ny = (yy - h / 2.0) / (h / 2.0)

    # Background thoracic soft tissue envelope
    img = np.clip(185.0 - 95.0 * (nx**2 * 0.8 + ny**2 * 0.5), 25.0, 220.0)

    # Left and Right radiolucent lung fields
    right_lung = ((nx + 0.36) / 0.28) ** 2 + ((ny + 0.04) / 0.58) ** 2
    left_lung = ((nx - 0.36) / 0.27) ** 2 + ((ny + 0.04) / 0.56) ** 2
    lung_mask = np.exp(-1.8 * right_lung) + np.exp(-1.8 * left_lung)
    img -= 115.0 * np.clip(lung_mask, 0.0, 1.0)

    # Mediastinal & cardiac silhouette
    heart = ((nx - 0.10) / 0.22) ** 2 + ((ny - 0.22) / 0.28) ** 2
    img += 85.0 * np.exp(-2.4 * heart)

    # Rib cage horizontal sinusoidal bands
    ribs = 14.0 * np.sin(ny * 28.0 + 0.35 * (nx**2)) * np.clip(lung_mask, 0.0, 1.0)
    img += ribs

    if focal_opacity:
        # Synthetic focal airspace opacity in Right Lower Thoracic Zone (viewer-left, lower lung)
        opacity_dist = ((nx + 0.34) / 0.16) ** 2 + ((ny - 0.18) / 0.16) ** 2
        img += 78.0 * np.exp(-2.8 * opacity_dist)

    arr_u8 = np.clip(img, 8.0, 248.0).astype(np.uint8)
    pil_img = Image.fromarray(arr_u8, mode="L")
    draw = ImageDraw.Draw(pil_img)
    draw.text((16, 14), "SYNTHETIC PHANTOM CXR - NOT REAL PATIENT DATA", fill=240)
    draw.text((16, h - 24), "MODALITY: CXR PA | CALIBRATION: SYNTHETIC RESEARCH", fill=230)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pil_img.save(output_path, format="PNG")
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return digest, w, h


def generate_synthetic_mri(output_path: Path) -> Tuple[str, int, int]:
    """
    Generates a clearly labeled synthetic 512x512 Axial T2-FLAIR Brain MRI phantom
    with cranial vault, cerebral hemispheres, lateral ventricles, and a synthetic
    focal hyperintensity in the left parieto-occipital region.
    """
    w, h = 512, 512
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2.0) / (w / 2.0)
    ny = (yy - h / 2.0) / (h / 2.0)

    ellipse = (nx / 0.72) ** 2 + (ny / 0.84) ** 2
    img = np.where(ellipse <= 1.0, 118.0 - 28.0 * ellipse, 10.0)

    # Cortical sulcal texture rings
    gyri = 12.0 * np.sin(nx * 22.0) * np.cos(ny * 22.0) * (ellipse <= 0.96)
    img += gyri

    # Lateral ventricles
    vent_l = ((nx - 0.11) / 0.08) ** 2 + ((ny + 0.02) / 0.22) ** 2
    vent_r = ((nx + 0.11) / 0.08) ** 2 + ((ny + 0.02) / 0.22) ** 2
    img -= 55.0 * (np.exp(-3.0 * vent_l) + np.exp(-3.0 * vent_r))

    # Focal FLAIR hyperintensity in Left Posterior Hemisphere
    lesion = ((nx - 0.30) / 0.13) ** 2 + ((ny - 0.26) / 0.13) ** 2
    img += 98.0 * np.exp(-3.2 * lesion)

    arr_u8 = np.clip(img, 5.0, 250.0).astype(np.uint8)
    pil_img = Image.fromarray(arr_u8, mode="L")
    draw = ImageDraw.Draw(pil_img)
    draw.text((16, 14), "SYNTHETIC PHANTOM MRI - NOT REAL PATIENT DATA", fill=240)
    draw.text((16, h - 24), "MODALITY: BRAIN MRI FLAIR | SYNTHETIC RESEARCH", fill=230)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pil_img.save(output_path, format="PNG")
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return digest, w, h
