import os
import sys
from pathlib import Path
from typing import List, Tuple
import numpy as np
import torch
import insightface
from insightface.app.common import Face

# -------------------------------------------------------------------------
# Dynamic Path Setup & InsightFace Patching
# -------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure monkeypatch is active to prevent INSwapper 'taskname' crashes
try:
    import reactor_patcher
    reactor_patcher.patch_insightface()
except Exception as patch_err:
    print(f"[ReActor] Warning: InsightFace monkeypatch could not be applied: {patch_err}")

# Folder paths from ComfyUI
try:
    import folder_paths
    MODELS_DIR = folder_paths.models_dir
except Exception:
    MODELS_DIR = os.path.join(REPO_ROOT.parents[1], "models")

# -------------------------------------------------------------------------
# Global Model Caches
# -------------------------------------------------------------------------
FS_MODEL = None
CURRENT_FS_MODEL_PATH = None
ANALYSIS_MODELS = {}

# -------------------------------------------------------------------------
# Provider Resolution (CUDA 12/13 & CPU Fallback)
# -------------------------------------------------------------------------
def get_execution_providers() -> List[str]:
    """Determine available ONNX Runtime providers with fallback."""
    providers = []
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available and torch.cuda.is_available():
            providers.append("CUDAExecutionProvider")
        if "CPUExecutionProvider" in available:
            providers.append("CPUExecutionProvider")
    except Exception:
        providers = ["CPUExecutionProvider"]
    return providers or ["CPUExecutionProvider"]


def get_insightface_path() -> str:
    """Return the base path to insightface models."""
    return os.path.join(MODELS_DIR, "insightface")


# -------------------------------------------------------------------------
# Face Analysis Model Loader
# -------------------------------------------------------------------------
def getAnalysisModel(det_size: Tuple[int, int] = (640, 640), model_name: str = "buffalo_l"):
    """
    Load or retrieve a cached FaceAnalysis instance.
    Includes fallback from CUDA to CPU if ONNX Runtime throws execution provider errors.
    """
    key = (model_name, det_size)
    if key in ANALYSIS_MODELS:
        return ANALYSIS_MODELS[key]

    root_path = get_insightface_path()
    providers = get_execution_providers()

    try:
        analyser = insightface.app.FaceAnalysis(
            name=model_name,
            providers=providers,
            root=root_path
        )
        analyser.prepare(ctx_id=0 if "CUDAExecutionProvider" in providers else -1, det_size=det_size)
    except Exception as e:
        print(f"[ReActor] Provider initialization failed with {providers}: {e}. Retrying with CPUExecutionProvider...")
        try:
            analyser = insightface.app.FaceAnalysis(
                name=model_name,
                providers=["CPUExecutionProvider"],
                root=root_path
            )
            analyser.prepare(ctx_id=-1, det_size=det_size)
        except Exception as err:
            raise RuntimeError(f"[ReActor] Failed to initialize FaceAnalysis ({model_name}): {err}") from err

    ANALYSIS_MODELS[key] = analyser
    return analyser


# -------------------------------------------------------------------------
# Face Swap Model Loader
# -------------------------------------------------------------------------
def getFaceSwapModel(model_path: str):
    """Load or retrieve the cached INSwapper ONNX model."""
    global FS_MODEL, CURRENT_FS_MODEL_PATH
    if FS_MODEL is not None and CURRENT_FS_MODEL_PATH == model_path:
        return FS_MODEL

    if not os.path.isfile(model_path):
        candidate = os.path.join(get_insightface_path(), os.path.basename(model_path))
        if os.path.isfile(candidate):
            model_path = candidate
        else:
            raise FileNotFoundError(f"[ReActor] Swapper model not found at '{model_path}' or '{candidate}'")

    providers = get_execution_providers()
    try:
        FS_MODEL = insightface.model_zoo.get_model(model_path, providers=providers)
    except Exception as e:
        print(f"[ReActor] Failed to load swapper on {providers}: {e}. Falling back to CPU...")
        FS_MODEL = insightface.model_zoo.get_model(model_path, providers=["CPUExecutionProvider"])

    CURRENT_FS_MODEL_PATH = model_path
    return FS_MODEL


# -------------------------------------------------------------------------
# Face Detection and Analysis
# -------------------------------------------------------------------------
def analyze_faces(img_data: np.ndarray, det_size: Tuple[int, int] = (640, 640), model_name: str = "buffalo_l") -> List[Face]:
    """
    Detect and extract faces from an image safely.
    Handles empty images, resizing, and detector exceptions gracefully.
    """
    if img_data is None or img_data.size == 0:
        return []

    analyser = getAnalysisModel(det_size, model_name=model_name)
    faces: List[Face] = []

    try:
        faces = analyser.get(img_data)
    except Exception as e:
        print(f"[ReActor] Warning during face detection: {e}")
        if det_size[0] > 320:
            try:
                fallback_analyser = getAnalysisModel((320, 320), model_name=model_name)
                faces = fallback_analyser.get(img_data)
            except Exception:
                faces = []

    if not faces:
        return []

    try:
        return sorted(faces, key=lambda x: x.bbox[0])
    except Exception:
        return faces


# -------------------------------------------------------------------------
# Swap Processing
# -------------------------------------------------------------------------
def swap_face(
    swap_model: any,
    target_img: np.ndarray,
    target_face: Face,
    source_face: Face,
) -> np.ndarray:
    """
    Execute face swap on target_face using source_face embedding.
    Fully uncensored; no SFW validation or masking checks invoked.
    """
    if target_img is None or target_face is None or source_face is None:
        return target_img

    try:
        result_img = swap_model.get(target_img, target_face, source_face, paste_back=True)
        return result_img
    except Exception as e:
        print(f"[ReActor] Error during face swapping: {e}")
        return target_img
