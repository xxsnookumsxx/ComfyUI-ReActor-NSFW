#!/usr/bin/env python3
"""
reactor_insightface_fix.py
===========================
Smart insightface installer for ComfyUI-ReActor-NSFW.

Strategy:
  Python 3.13  -> build from source (only real cp313 option)
  Python 3.12  -> Gourieff cp312 prebuilt wheel (genuine)
  Python 3.11  -> Gourieff cp311 prebuilt wheel (genuine)
  Python 3.10  -> Gourieff cp310 prebuilt wheel (genuine)
  Other        -> pip default

Also patches face3d mesh_core_cython to be import-safe on all versions.

Usage:
    python reactor_insightface_fix.py
    python reactor_insightface_fix.py --build-only
    python reactor_insightface_fix.py --patch-only
"""

import sys
import os
import subprocess
import platform
import shutil
import argparse
import importlib.util

# ── Colour helpers ──────────────────────────────────────────────────────────
def green(s):  return f"\033[92m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def cyan(s):   return f"\033[96m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"

# ── Constants ────────────────────────────────────────────────────────────────

INSIGHTFACE_VERSION = "0.7.3"
PY = sys.version_info
IS_WIN = platform.system() == "Windows"
ARCH = platform.machine().lower()
IS_X64 = "amd64" in ARCH or "x86_64" in ARCH

# Gourieff prebuilt wheels (genuine for these versions)
GOURIEFF_BASE = "https://github.com/Gourieff/Assets/raw/main/Insightface"
GOURIEFF_WHEELS = {
    (3, 12): f"{GOURIEFF_BASE}/insightface-0.7.3-cp312-cp312-win_amd64.whl",
    (3, 11): f"{GOURIEFF_BASE}/insightface-0.7.3-cp311-cp311-win_amd64.whl",
    (3, 10): f"{GOURIEFF_BASE}/insightface-0.7.3-cp310-cp310-win_amd64.whl",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def pip(args, check=True):
    cmd = [sys.executable, "-m", "pip"] + args
    print(cyan(f"  $ {' '.join(cmd)}"))
    result = subprocess.run(cmd, capture_output=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"pip command failed: {' '.join(args)}")
    return result.returncode == 0

def check_insightface_ok():
    """Return True if insightface imports cleanly."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import insightface; from insightface.app.common import Face; print('OK')"],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0 and "OK" in result.stdout
    except Exception:
        return False

def check_build_tools():
    """Check if MSVC or gcc is available for source builds."""
    if IS_WIN:
        # Check for cl.exe (MSVC)
        cl = shutil.which("cl")
        if cl:
            print(green("  ✔ MSVC compiler found"))
            return True
        # Check for VS Build Tools via vswhere
        vswhere = (
            r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
        )
        if os.path.exists(vswhere):
            result = subprocess.run([vswhere, "-latest", "-property", "installationPath"],
                                     capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                print(green(f"  ✔ Visual Studio found: {result.stdout.strip()}"))
                return True
        print(yellow("  ⚠ No MSVC compiler found. Build tools required for Python 3.13."))
        print(yellow("    Install from: https://visualstudio.microsoft.com/visual-cpp-build-tools/"))
        return False
    else:
        gcc = shutil.which("gcc") or shutil.which("cc")
        if gcc:
            print(green(f"  ✔ C compiler found: {gcc}"))
            return True
        print(yellow("  ⚠ No C compiler found. Install build-essential (Linux) or Xcode tools (Mac)."))
        return False

def find_insightface_site():
    """Find insightface install path in site-packages."""
    for path in sys.path:
        candidate = os.path.join(path, "insightface")
        if os.path.isdir(candidate):
            return candidate
    return None

# ── Step 1: Install insightface ──────────────────────────────────────────────

def install_insightface():
    py_key = (PY.major, PY.minor)
    print(bold(f"\n── Installing insightface {INSIGHTFACE_VERSION} for Python {PY.major}.{PY.minor} ──"))

    # Python 3.13 → source build (only real option)
    if py_key == (3, 13):
        print(yellow("  Python 3.13 detected. No genuine prebuilt wheel exists."))
        print(yellow("  Will attempt source build (requires C++ compiler).\n"))

        if not check_build_tools():
            print(red("\n  ✘ Cannot build without a C++ compiler."))
            print(yellow("  Falling back to: applying import stub patch only."))
            print(yellow("  Face swap will work; 3D mesh features will be stubbed out."))
            return "stub_only"

        # Ensure build deps
        print(cyan("  Installing build dependencies..."))
        pip(["install", "--upgrade", "setuptools", "wheel", "cython", "numpy>=2.0.0"])

        # Uninstall any existing mislabeled version
        pip(["uninstall", "insightface", "-y"], check=False)

        # Build from source - no binary
        print(cyan(f"  Building insightface=={INSIGHTFACE_VERSION} from source..."))
        print(yellow("  This may take 3-5 minutes.\n"))
        success = pip([
            "install",
            f"insightface=={INSIGHTFACE_VERSION}",
            "--no-binary", "insightface",
            "--no-cache-dir",
        ], check=False)

        if success:
            print(green("  ✔ Source build succeeded!"))
            return "built"
        else:
            print(red("  ✘ Source build failed."))
            print(yellow("  Applying stub patch as fallback."))
            return "stub_only"

    # Python 3.12, 3.11, 3.10 → genuine Gourieff wheel
    elif py_key in GOURIEFF_WHEELS and IS_WIN and IS_X64:
        wheel_url = GOURIEFF_WHEELS[py_key]
        print(green(f"  Using genuine Gourieff wheel for Python {PY.major}.{PY.minor}"))
        pip(["uninstall", "insightface", "-y"], check=False)
        pip(["install", wheel_url, "--force-reinstall"])
        return "prebuilt"

    # Other: pip default
    else:
        print(cyan("  Using pip default install (non-Windows or non-x64)"))
        pip(["uninstall", "insightface", "-y"], check=False)
        pip(["install", f"insightface=={INSIGHTFACE_VERSION}"])
        return "pip"

# ── Step 2: Patch face3d mesh_core_cython ────────────────────────────────────

def patch_face3d():
    print(bold("\n── Patching face3d mesh_core_cython import ──"))

    insightface_dir = find_insightface_site()
    if not insightface_dir:
        print(yellow("  insightface not found in site-packages, skipping patch"))
        return False

    target = os.path.join(
        insightface_dir,
        "thirdparty", "face3d", "mesh", "__init__.py"
    )

    if not os.path.exists(target):
        print(yellow(f"  Target not found: {target}"))
        return False

    with open(target, "r", encoding="utf-8") as f:
        content = f.read()

    OLD = "from .cython import mesh_core_cython"
    NEW = (
        "try:\n"
        "    from .cython import mesh_core_cython\n"
        "except (ImportError, OSError, Exception):\n"
        "    # Python version mismatch or missing compiled extension\n"
        "    # mesh_core_cython is only used for 3D face reconstruction,\n"
        "    # not face swapping. Safe to stub out for ReActor usage.\n"
        "    mesh_core_cython = None"
    )

    if "mesh_core_cython = None" in content:
        print(green("  ✔ Patch already applied"))
        return True

    if OLD in content:
        backup = target + ".bak"
        shutil.copy2(target, backup)
        print(cyan(f"  Backed up -> {backup}"))
        content = content.replace(OLD, NEW)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        print(green(f"  ✔ Patched: {target}"))
        return True
    else:
        print(yellow(f"  Expected import line not found in {target}"))
        print(yellow("  The insightface version may have changed — check manually"))
        return False

# ── Step 3: Verify ────────────────────────────────────────────────────────────

def verify():
    print(bold("\n── Verifying insightface import ──"))
    if check_insightface_ok():
        print(green("  ✔ insightface imports cleanly!"))
        return True
    else:
        print(red("  ✘ insightface still failing to import"))
        print(yellow("  Run ComfyUI and paste the new error here for further diagnosis."))
        return False

# ── Step 4: Print summary ─────────────────────────────────────────────────────

def summary(install_result, patch_ok, verify_ok):
    print(bold(cyan("\n══════════════════════════════════════════")))
    print(bold("  INSIGHTFACE SETUP SUMMARY"))
    print(bold(cyan("══════════════════════════════════════════")))
    print(f"  Python version   : {bold(f'{PY.major}.{PY.minor}.{PY.micro}')}")

    install_labels = {
        "built":     green("Built from source (genuine cp313)"),
        "prebuilt":  green("Genuine Gourieff prebuilt wheel"),
        "pip":       green("pip default install"),
        "stub_only": yellow("Existing install kept (stub patch applied)"),
        "skipped":   yellow("Skipped (--patch-only)"),
    }
    print(f"  Install method   : {install_labels.get(install_result, install_result)}")
    print(f"  face3d patched   : {green('Yes') if patch_ok else red('No')}")
    print(f"  Import test      : {green('PASS') if verify_ok else red('FAIL')}")

    if verify_ok:
        print(green("\n  ✔ Ready! Restart ComfyUI and ReActor should load cleanly."))
    else:
        print(red("\n  ✘ Still issues — check the error output above."))
    print(bold(cyan("══════════════════════════════════════════\n")))

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Smart insightface installer for ComfyUI-ReActor-NSFW"
    )
    parser.add_argument("--build-only",  action="store_true",
                        help="Only install/build insightface, skip patch")
    parser.add_argument("--patch-only",  action="store_true",
                        help="Only apply face3d stub patch, skip install")
    parser.add_argument("--force-build", action="store_true",
                        help="Force source build even if import already works")
    args = parser.parse_args()

    print(bold(cyan("\n════════════════════════════════════════════")))
    print(bold(cyan("  ReActor insightface Smart Installer")))
    print(bold(cyan(f"  Python {PY.major}.{PY.minor}.{PY.micro} | {platform.system()} {ARCH}")))
    print(bold(cyan("════════════════════════════════════════════\n")))

    # Quick check — already working?
    if not args.force_build and not args.patch_only:
        if check_insightface_ok():
            print(green("  insightface already imports cleanly."))
            print(cyan("  Applying safety patch to face3d anyway...\n"))
            patch_ok = patch_face3d()
            summary("skipped", patch_ok, True)
            return

    install_result = "skipped"
    if not args.patch_only:
        install_result = install_insightface()

    patch_ok = True
    if not args.build_only:
        patch_ok = patch_face3d()

    verify_ok = verify()
    summary(install_result, patch_ok, verify_ok)

if __name__ == "__main__":
    main()