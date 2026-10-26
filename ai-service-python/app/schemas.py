from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class AnalyzeImageRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=128)
    image_id: str = Field(..., min_length=1, max_length=128)
    image_path: str = Field(..., min_length=1, max_length=1024)
    output_overlay_path: str = Field(..., min_length=1, max_length=1024)
    modality: Literal["CXR", "MRI"] = Field(..., description="Supported medical imaging modality")
    body_part: str = Field(default="CHEST", max_length=64)
    xai_method: Literal["GRAD_CAM", "GRAD_CAM_PLUS_OCCLUSION"] = Field(default="GRAD_CAM")
    target_class_index: Optional[int] = Field(
        default=None,
        description="Optional class index to explain; defaults to top predicted class",
    )


class ImageMetadataReport(BaseModel):
    sha256_digest: str
    format: str
    mode: str
    width: int
    height: int
    aspect_ratio: float
    bit_depth: int
    min_intensity: float
    max_intensity: float
    mean_intensity: float
    std_intensity: float
    dynamic_range: float
    orientation: str
    preprocessing_steps: List[str]


class ClassScoreItem(BaseModel):
    class_index: int
    class_code: str
    class_label: str
    probability: float
    logit: float
    snomed_code: str
    loinc_code: str


class RegionAttributionItem(BaseModel):
    region_name: str
    quadrant_code: str
    mean_attribution: float
    peak_attribution: float
    bbox_norm: List[float]  # [x1, y1, x2, y2] normalized 0..1


class XaiArtifactReport(BaseModel):
    method: str
    explained_class_code: str
    explained_class_label: str
    explained_class_index: int
    target_layer: str
    feature_map_resolution: str
    upsampled_resolution: str
    overlay_path: str
    overlay_sha256: str
    peak_coords_norm: List[float]  # [x_norm, y_norm]
    active_area_ratio: float
    top_regions: List[RegionAttributionItem]
    color_scale_legend: Dict[str, str]
    clinical_warning: str
    localization_limitation: str


class AnalyzeImageResponse(BaseModel):
    job_id: str
    image_id: str
    status: Literal["COMPLETED"]
    model_id: str
    model_version: str
    model_architecture: str
    calibration_status: Literal["RESEARCH_UNVERIFIED", "CUSTOM_CHECKPOINT"]
    execution_device: str
    inference_duration_ms: float
    modality: str
    image_metadata: ImageMetadataReport
    predicted_class_code: str
    predicted_class_label: str
    predicted_probability: float
    shannon_entropy: float
    uncertainty_level: Literal["LOW", "MODERATE", "HIGH_UNCERTAINTY"]
    uncertainty_reason: str
    class_scores: List[ClassScoreItem]
    xai: XaiArtifactReport
    limitations: List[str]
    clinical_safety_notice: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[str] = None
