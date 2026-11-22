"""Reproducible PyTorch medical imaging dataset & DenseNet-121 training pipeline."""

from .dataset import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    MODALITY_CLASS_CODES,
    MedicalImagingDataset,
    build_synthetic_benchmark_records,
    load_manifest_records,
    patient_level_stratified_split,
    preprocess_gray_array_to_tensor,
)

__all__ = [
    "IMAGENET_MEAN",
    "IMAGENET_STD",
    "MODALITY_CLASS_CODES",
    "MedicalImagingDataset",
    "build_synthetic_benchmark_records",
    "load_manifest_records",
    "patient_level_stratified_split",
    "preprocess_gray_array_to_tensor",
]
