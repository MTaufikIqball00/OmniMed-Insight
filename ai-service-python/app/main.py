import hmac
import os
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
import torch

from .imaging import ImageValidationError
from .schemas import AnalyzeImageRequest, AnalyzeImageResponse
from .xai_engine import MODALITY_CLASS_CATALOG, MedicalDenseNetXaiEngine

app = FastAPI(
    title="OmniMed Insight — Internal Medical AI & XAI Inference Service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

ENGINE: Optional[MedicalDenseNetXaiEngine] = None


def get_engine() -> MedicalDenseNetXaiEngine:
    global ENGINE
    if ENGINE is None:
        ENGINE = MedicalDenseNetXaiEngine()
    return ENGINE


def verify_internal_token(
    x_internal_service_token: Optional[str] = Header(default=None),
) -> None:
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SERVICE_TOKEN_UNCONFIGURED",
                "message": "INTERNAL_SERVICE_TOKEN environment variable is not configured.",
            },
        )
    if not x_internal_service_token or not hmac.compare_digest(
        x_internal_service_token.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "UNAUTHORIZED_INTERNAL_CALLER",
                "message": "Invalid or missing X-Internal-Service-Token header.",
            },
        )


@app.on_event("startup")
def on_startup() -> None:
    get_engine()


@app.exception_handler(ImageValidationError)
async def handle_image_validation_error(_request: Request, exc: ImageValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
        },
    )


@app.get("/health")
def health_check() -> Dict[str, Any]:
    eng = get_engine()
    return {
        "service": "omnimed-ai-inference-python",
        "status": "healthy",
        "pytorch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "execution_device": eng.device_label,
        "model_id": "omnimed-densenet121-xai",
        "model_version": eng.model_version,
        "model_architecture": "DenseNet-121 (PyTorch Differentiable Vision Backbone + Grad-CAM Hook)",
        "calibration_status": eng.calibration_status,
        "supported_modalities": ["CXR", "MRI"],
        "supported_xai_methods": ["GRAD_CAM", "GRAD_CAM_PLUS_OCCLUSION"],
        "external_llm_status": "DISABLED_FOR_PHI_GOVERNANCE",
        "clinical_disclaimer": (
            "Research-calibrated PyTorch DenseNet-121 + Grad-CAM service. "
            "Outputs are decision-support aids and are not clinically validated for autonomous diagnosis."
        ),
    }


@app.get("/internal/v1/models", dependencies=[Depends(verify_internal_token)])
def list_models() -> Dict[str, Any]:
    eng = get_engine()
    return {
        "models": [
            {
                "model_id": "omnimed-densenet121-xai",
                "model_version": eng.model_version,
                "architecture": "DenseNet-121 (TorchVision PyTorch)",
                "calibration_status": eng.calibration_status,
                "execution_device": eng.device_label,
                "supported_modalities": ["CXR", "MRI"],
                "supported_xai_methods": ["GRAD_CAM", "GRAD_CAM_PLUS_OCCLUSION"],
                "target_layer": "features.denseblock4",
                "classes_by_modality": MODALITY_CLASS_CATALOG,
                "status": "IMPLEMENTED_AND_READY",
            },
            {
                "model_id": "med-palm-2-external",
                "model_version": "N/A",
                "architecture": "External Cloud Multimodal LLM",
                "calibration_status": "UNAVAILABLE",
                "execution_device": "N/A",
                "supported_modalities": [],
                "supported_xai_methods": [],
                "target_layer": "N/A",
                "classes_by_modality": {},
                "status": "UNAVAILABLE_EXTERNAL_API_DISABLED",
            },
        ]
    }


@app.post(
    "/internal/v1/analyze",
    response_model=AnalyzeImageResponse,
    dependencies=[Depends(verify_internal_token)],
)
def analyze_medical_image(payload: AnalyzeImageRequest) -> AnalyzeImageResponse:
    eng = get_engine()
    return eng.analyze(payload)
