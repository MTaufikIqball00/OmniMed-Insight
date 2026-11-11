from contextlib import asynccontextmanager
import hmac
import json
import os
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
import torch

from .imaging import ImageValidationError
from .schemas import (
    AnalyzeImageRequest,
    AnalyzeImageResponse,
    IcuPredictRequest,
    IcuPredictResponse,
)
from .xai_engine import MODALITY_CLASS_CATALOG, MedicalDenseNetXaiEngine
from .icu_engine import IcuEarlyWarningEngine

ENGINE: Optional[MedicalDenseNetXaiEngine] = None
ICU_ENGINE: Optional[IcuEarlyWarningEngine] = None


def get_engine() -> MedicalDenseNetXaiEngine:
    global ENGINE
    if ENGINE is None:
        ENGINE = MedicalDenseNetXaiEngine()
    return ENGINE


def get_icu_engine() -> IcuEarlyWarningEngine:
    global ICU_ENGINE
    if ICU_ENGINE is None:
        ICU_ENGINE = IcuEarlyWarningEngine()
    return ICU_ENGINE


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_engine()
    yield


app = FastAPI(
    title="OmniMed Insight — Internal Medical AI & XAI Inference Service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


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
            {
                "model_id": "omnimed-icu-lightgbm-v1",
                "model_version": "1.0.0",
                "architecture": "LightGBM + SHAP TreeExplainer (Temporal Sepsis-3 Early Warning)",
                "calibration_status": "VALIDATED_TEST_COHORT",
                "execution_device": "CPU",
                "prediction_horizon": "6_to_12_hours",
                "decision_threshold": 0.05,
                "supported_modalities": ["ICU_LONGITUDINAL_VITALS_AND_LABS"],
                "supported_xai_methods": ["TREE_SHAP_FEATURE_ATTRIBUTION"],
                "target_endpoint": "SEPSIS_DETERIORATION",
                "status": "IMPLEMENTED_AND_READY",
            },
            {
                "model_id": "omnimed-icu-cohort-lgbm-v1",
                "model_version": "1.0.0",
                "architecture": "LightGBM + SHAP TreeExplainer (Archive2 5,000-Patient ICU Cohort)",
                "calibration_status": "VALIDATED_TEST_COHORT",
                "execution_device": "CPU",
                "prediction_horizon": "ICU_ADMISSION_AND_STAY",
                "decision_threshold": 0.05,
                "supported_modalities": ["ICU_COHORT_CLINICAL_PANEL"],
                "supported_xai_methods": ["TREE_SHAP_FEATURE_ATTRIBUTION"],
                "target_endpoint": "SEPSIS_AND_CHF_DETERIORATION",
                "status": "IMPLEMENTED_AND_READY",
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


@app.post(
    "/internal/v1/icu/predict",
    response_model=IcuPredictResponse,
    dependencies=[Depends(verify_internal_token)],
)
def predict_icu_risk(payload: IcuPredictRequest) -> IcuPredictResponse:
    eng = get_icu_engine()
    obs_dicts = [o.model_dump() for o in payload.observations]
    res = eng.predict(
        stay_id=payload.stay_id,
        patient_id=payload.patient_id,
        current_iculos=payload.current_iculos,
        observations=obs_dicts,
        age=payload.age if payload.age is not None else 65.0,
        gender=payload.gender if payload.gender is not None else 0.0,
    )
    return IcuPredictResponse(**res)


@app.get(
    "/internal/v1/icu/models",
    dependencies=[Depends(verify_internal_token)],
)
def get_icu_model_metadata() -> Dict[str, Any]:
    eng = get_icu_engine()
    res = dict(eng.meta)
    cohort_meta_file = eng.models_dir / "cohort_champion_meta.json"
    if cohort_meta_file.exists():
        with open(cohort_meta_file, "r", encoding="utf-8") as f:
            res["cohort_model"] = json.load(f)
    return res

