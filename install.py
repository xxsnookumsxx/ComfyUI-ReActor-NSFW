import os
import sys
import shutil
import platform
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from importlib.metadata import distribution, PackageNotFoundError
from tqdm import tqdm
from packaging import version as pv

try:
    import folder_paths
    models_dir = folder_paths.models_dir
except Exception:
    models_dir = os.path.join(Path(__file__).parents[2], "models")

# Define model paths
insightface_dir = os.path.join(models_dir, "insightface")
swapper_model_path = os.path.join(insightface_dir, "inswapper_128.onnx")
submodels_dir = os.path.join(insightface_dir, "models")
buffalo_l_dir = os.path.join(submodels_dir, "buffalo_l")

SWAPPER_URL = "https://huggingface.co/datasets/Gourieff/ReActor/resolve/main/models/inswapper_128.onnx"
BUFFALO_L_ZIP_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"

INSIGHTFACE_WHEELS = {
    (3, 10): "https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp310-cp310-win_amd64.whl",
    (3, 11): "https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp311-cp311-win_amd64.whl",
    (3, 12): "https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp312-cp312-win_amd64.whl",
    (3, 13): "https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp313-cp313-win_amd64.whl",
}

def run_pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-warn-script-location", *args], check=False)

def is_installed(package: str, version: str = None, strict: bool = True):
    try:
        pkg_name = package.split("==")[0].split(">=")[0].split("<")[0].strip()
        dist = distribution(pkg_name)
        if version is not None:
            installed_ver = dist.version
            if (installed_ver != version and strict) or (pv.parse(installed_ver) < pv.parse(version) and not strict):
                return False
        return True
    except PackageNotFoundError:
        return False
    except Exception:
        return False

def download_file(url, target_path, desc):
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    request = urllib.request.urlopen(url)
    total = int(request.headers.get("Content-Length", 0))
    with tqdm(total=total, desc=f"[ReActor] Downloading {desc}", unit="B", unit_scale=True, unit_divisor=1024) as progress:
        urllib.request.urlretrieve(url, target_path, reporthook=lambda count, block_size, total_size: progress.update(block_size))

def clean_misplaced_models():
    """Ensure inswapper is not sitting inside antelopev2 or buffalo_l subdirectories."""
    for pack in ["antelopev2", "buffalo_l"]:
        pack_folder = os.path.join(submodels_dir, pack)
        if os.path.exists(pack_folder):
            misplaced = os.path.join(pack_folder, "inswapper_128.onnx")
            if os.path.exists(misplaced):
                print(f"[ReActor] Found misplaced inswapper_128.onnx in {pack_folder}. Relocating...")
                if not os.path.exists(swapper_model_path):
                    shutil.move(misplaced, swapper_model_path)
                else:
                    os.remove(misplaced)

print("[ReActor] Checking directories and models...")
os.makedirs(insightface_dir, exist_ok=True)
os.makedirs(buffalo_l_dir, exist_ok=True)
clean_misplaced_models()

# 1. Download inswapper_128.onnx if missing
if not os.path.exists(swapper_model_path):
    download_file(SWAPPER_URL, swapper_model_path, "inswapper_128.onnx")

# 2. Download buffalo_l detector pack if missing
buffalo_files = ["1k3d68.onnx", "2d106det.onnx", "genderage.onnx", "glintr100.onnx", "det_10g.onnx"]
if not all(os.path.exists(os.path.join(buffalo_l_dir, f)) for f in buffalo_files):
    zip_dest = os.path.join(insightface_dir, "buffalo_l.zip")
    download_file(BUFFALO_L_ZIP_URL, zip_dest, "buffalo_l pack")
    print("[ReActor] Extracting buffalo_l models...")
    with zipfile.ZipFile(zip_dest, "r") as zip_ref:
        zip_ref.extractall(buffalo_l_dir)
    if os.path.exists(zip_dest):
        os.remove(zip_dest)

# 3. Install InsightFace wheel
if not is_installed("insightface"):
    py_ver = (sys.version_info.major, sys.version_info.minor)
    if platform.system() == "Windows" and py_ver in INSIGHTFACE_WHEELS:
        print(f"[ReActor] Installing prebuilt InsightFace wheel for Python {py_ver[0]}.{py_ver[1]}...")
        run_pip(INSIGHTFACE_WHEELS[py_ver])
    else:
        run_pip("insightface==0.7.3")

# 4. Install ONNX Runtime
try:
    import torch
    cuda_ver = torch.version.cuda
    if not torch.cuda.is_available():
        if not is_installed("onnxruntime", "1.19.0", False):
            run_pip("onnxruntime", "-U")
    else:
        if not is_installed("onnxruntime-gpu", "1.20.1", False):
            run_pip("onnxruntime-gpu", "-U")
except Exception:
    run_pip("onnxruntime", "-U")

# 5. Install requirements.txt
req_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "requirements.txt")
if os.path.exists(req_file):
    run_pip("-r", req_file)

print("[ReActor] Setup complete and models placed correctly.")
