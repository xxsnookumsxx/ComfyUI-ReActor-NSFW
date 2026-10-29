# scripts/reactor_sfw.py
import logging

MODEL_EXISTS = True
SCORE = 999.0

def ensure_nsfw_model(nsfwdet_model_path):
    """Bypassed: Never download or verify the NSFW detector model."""
    return True

def nsfw_image(img_data, model_path: str):
    """Bypassed: Always return False (image is not NSFW)."""
    return False
