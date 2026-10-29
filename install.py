import subprocess
import os
import sys
import platform
import urllib.request
from pathlib import Path
from importlib.metadata import distribution, PackageNotFoundError
from tqdm import tqdm
from packaging import version as pv

try:
    from folder_paths import models_dir
except ImportError:
    models_dir = os.path.join(Path(__file__).parents[2], "models")

req_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "requirements.txt")
model_url = "https://huggingface.co/datasets/Gourieff/ReActor/resolve/main/models/inswapper_128.onnx"
model_name = os.path.basename(model_url)
models_dir_path = os.path.join(models_dir, "insightface")
model_path = os.path.join(models_dir_path, model_name)

# Pre-compiled InsightFace wheels for Windows
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
            installed_version = dist.version
            if (installed_version != version and strict) or (pv.parse(installed_version) < pv.parse(version) and not strict):
                return False
        return True
    except PackageNotFoundError:
        return False
    except Exception:
        return False

def download(url, path, name):
    request = urllib.request.urlopen(url)
    total = int(request.headers.get("Content-Length", 0))
    with tqdm(total=total, desc=f"[ReActor] Downloading {name} to {path}", unit="B", unit_scale=True, unit_divisor=1024) as progress:
        urllib.request.urlretrieve(url, path, reporthook=lambda count, block_size, total_size: progress.update(block_size))

if not os.path.exists(models_dir_path):
    os.makedirs(models_dir_path, exist_ok=True)

if not os.path.exists(model_path):
    download(model_url, model_path, model_name)

# 1. Install InsightFace (using prebuilt wheel on Windows Python 3.10-3.13)
if not is_installed("insightface"):
    py_ver = (sys.version_info.major, sys.version_info.minor)
    if platform.system() == "Windows" and py_ver in INSIGHTFACE_WHEELS:
        print(f"[ReActor] Installing prebuilt InsightFace wheel for Python {py_ver[0]}.{py_ver[1]}...")
        run_pip(INSIGHTFACE_WHEELS[py_ver])
    else:
        run_pip("insightface==0.7.3")

# 2. Install ONNX Runtime (Compatible with CUDA 12/13 & CPU fallback)
try:
    import torch
    cuda_version = torch.version.cuda
    if not torch.cuda.is_available():
        ort = "onnxruntime"
        if not is_installed(ort, "1.19.0", False):
            run_pip(ort, "-U")
    else:
        ort = "onnxruntime-gpu"
        print(f"[ReActor] Torch: {torch.__version__} (CUDA {cuda_version})")
        if not is_installed(ort, "1.20.1", False):
            run_pip(ort, "-U")
        # Ensure standard onnxruntime is also present as fallback for CUDA 13.0 nightly environments
        if cuda_version and float(cuda_version.split(".")[0]) >= 13:
            print("[ReActor] CUDA 13.x detected. Note: If onnxruntime-gpu lacks cu13 DLLs, ONNX will gracefully use CPU.")
except Exception as e:
    print(f"[ReActor] Warning during ONNX Runtime check: {e}")
    run_pip("onnxruntime", "-U")

# 3. Install remaining requirements.txt packages
if os.path.exists(req_file):
    with open(req_file, "r", encoding="utf-8") as file:
        for line in file:
            package = line.strip()
            if not package or package.startswith("#"):
                continue
            strict = True
            package_version = None
            if "==" in package:
                package_version = package.split("==")[1].split("<")[0].strip()
            elif ">=" in package:
                package_version = package.split(">=")[1].split(",")[0].strip()
                strict = False
            if not is_installed(package, package_version, strict):
                run_pip(package)

print("[ReActor] Installation Complete (Uncensored / Python 3.13 Ready).")
