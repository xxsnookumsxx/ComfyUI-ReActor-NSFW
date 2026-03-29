#!/usr/bin/env python3
"""
reactor_py313_patch.py
======================
Patches ComfyUI-ReActor-NSFW for Python 3.13 + NumPy 2.x compatibility.

Usage:
    python reactor_py313_patch.py
    python reactor_py313_patch.py "C:/ComfyUI/custom_nodes/ComfyUI-ReActor-NSFW"
    python reactor_py313_patch.py --dry-run

What it fixes:
    - pkg_resources  -> importlib.metadata  (removed in Python 3.12+)
    - distutils      -> packaging.version   (removed in Python 3.12+)
    - numpy==1.26.4 pin in pyproject.toml   -> numpy>=2.0.0
    - numpy>=2.22.0 typo in requirements    -> numpy>=2.0.0
    - deprecated numpy type aliases (np.bool, np.int, np.float, np.complex,
      np.object, np.str)                    -> np.bool_, np.int_, np.float64, etc.
    - albumentations pinned below 2.0 to avoid breaking API changes
    - onnx version floor raised to 1.18.0   (first with Python 3.13 wheels)
    - insightface line commented out        (handled by separate wheel install)
    - importlib_metadata standalone dep     removed (now using stdlib)

Safety:
    Every modified file gets a .bak backup before writing.
"""

import os
import re
import sys
import shutil
import argparse

# ── Colour helpers ──────────────────────────────────────────────────────────

def green(s):  return f"\033[92m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def cyan(s):   return f"\033[96m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"

# ── Helpers ──────────────────────────────────────────────────────────────────

def read_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def write_file(path, content, dry_run=False):
    if dry_run:
        print(yellow(f"  [DRY-RUN] Would write: {path}"))
        return
    backup = path + ".bak"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        print(cyan(f"  Backed up -> {backup}"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def patch_file(path, patches, dry_run=False):
    """
    patches: list of (description, old_regex_or_str, new_str, use_regex)
    Returns True if any changes were made.
    """
    original = read_file(path)
    content = original
    changed = False

    for desc, old, new, use_regex in patches:
        if use_regex:
            new_content = re.sub(old, new, content, flags=re.MULTILINE | re.DOTALL)
        else:
            new_content = content.replace(old, new)

        if new_content != content:
            print(green(f"  ✔ {desc}"))
            content = new_content
            changed = True
        else:
            # Check if the fix is already applied (idempotent)
            pass

    if changed:
        write_file(path, content, dry_run)
    else:
        print(f"  (no changes needed)")

    return changed

# ── Per-file patch definitions ───────────────────────────────────────────────

def patch_install_py(path, dry_run=False):
    print(bold(f"\n[install.py] {path}"))

    original = read_file(path)
    content = original

    # 1. Replace the pkg_resources / importlib_metadata import block
    old_pkg = r"""try:\s*from pkg_resources import get_distribution as distributions\s*except[^\n]*\n\s*from importlib_metadata import distributions"""
    new_pkg = (
        "# Python 3.13 compat: pkg_resources removed; use stdlib importlib.metadata\n"
        "try:\n"
        "    from importlib.metadata import packages_distributions as _pkg_dist\n"
        "    from importlib.metadata import version as _pkg_version\n"
        "    def distributions(pkg=None):\n"
        "        if pkg:\n"
        "            try:\n"
        "                return [type('D', (), {'version': _pkg_version(pkg)})()\n"
        "                        ]\n"
        "            except Exception:\n"
        "                return []\n"
        "        return []\n"
        "except Exception:\n"
        "    def distributions(pkg=None):\n"
        "        return []"
    )
    content_new = re.sub(old_pkg, new_pkg, content, flags=re.MULTILINE | re.DOTALL)
    if content_new != content:
        print(green("  ✔ Replaced pkg_resources block with importlib.metadata"))
        content = content_new
    else:
        # Also catch simple single-line imports
        if "from pkg_resources import" in content:
            content = content.replace(
                "from pkg_resources import",
                "# [py313-patch] from pkg_resources import  # removed - use importlib.metadata\n# from pkg_resources import"
            )
            print(green("  ✔ Commented out leftover pkg_resources import"))

    # 2. Replace standalone importlib_metadata import
    content = re.sub(
        r"^(import importlib_metadata|from importlib_metadata import)",
        r"# [py313-patch] \1  # replaced with stdlib importlib.metadata",
        content,
        flags=re.MULTILINE
    )

    # 3. Fix torch version comparison - add safe version helper if not present
    torch_helper = (
        "\n\n# [py313-patch] Safe torch version comparison helper\n"
        "def _tv(ver_str):\n"
        "    \"\"\"Parse a torch version string safely, stripping +cu suffixes.\"\"\"\n"
        "    try:\n"
        "        from packaging.version import Version\n"
        "        clean = ver_str.split('+')[0].split('a')[0].split('b')[0].split('rc')[0]\n"
        "        return Version(clean)\n"
        "    except Exception:\n"
        "        return None\n\n"
        "def _tv_gte(installed, required):\n"
        "    v = _tv(installed)\n"
        "    return v is not None and v >= _tv(required)\n\n"
        "def _tv_lt(installed, required):\n"
        "    v = _tv(installed)\n"
        "    return v is not None and v < _tv(required)\n"
    )
    if "_tv_gte" not in content and "torch" in content:
        # Insert after imports block - find first non-import line
        import_end = 0
        for i, line in enumerate(content.split('\n')):
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ', '#', '"""', "'''", '')) :
                import_end = i
            else:
                break
        lines = content.split('\n')
        lines.insert(import_end + 1, torch_helper)
        content = '\n'.join(lines)
        print(green("  ✔ Injected safe torch version helper (_tv_gte / _tv_lt)"))

    # 4. Add insightface wheel installer function
    insightface_installer = (
        "\n\n# [py313-patch] Auto-install insightface from prebuilt Python 3.13 wheel\n"
        "def ensure_insightface():\n"
        "    import sys, subprocess, platform\n"
        "    try:\n"
        "        import insightface\n"
        "        return  # already installed\n"
        "    except ImportError:\n"
        "        pass\n"
        "    py = sys.version_info\n"
        "    if py.major == 3 and py.minor == 13:\n"
        "        machine = platform.machine().lower()\n"
        "        system = platform.system().lower()\n"
        "        if system == 'windows' and 'amd64' in machine or 'x86_64' in machine:\n"
        "            wheel = ('https://github.com/Gourieff/Assets/raw/main/Insightface/'\n"
        "                     'insightface-0.7.3-cp313-cp313-win_amd64.whl')\n"
        "        elif system == 'linux' and 'x86_64' in machine:\n"
        "            wheel = ('https://github.com/Gourieff/Assets/raw/main/Insightface/'\n"
        "                     'insightface-0.7.3-cp313-cp313-linux_x86_64.whl')\n"
        "        else:\n"
        "            wheel = 'insightface==0.7.3'\n"
        "        print(f'[ReActor] Installing insightface for Python 3.13 from: {wheel}')\n"
        "        subprocess.check_call([sys.executable, '-m', 'pip', 'install', wheel])\n"
        "    else:\n"
        "        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'insightface==0.7.3'])\n"
    )
    if "ensure_insightface" not in content:
        content += insightface_installer
        print(green("  ✔ Added ensure_insightface() wheel installer for Python 3.13"))

    if content != original:
        write_file(path, content, dry_run)
        return True
    print("  (no changes needed)")
    return False


def patch_requirements_txt(path, dry_run=False):
    print(bold(f"\n[requirements.txt] {path}"))

    patches = [
        (
            "numpy: fix version to >=2.0.0",
            r"^numpy[>=!<~^].*$",
            "numpy>=2.0.0",
            True
        ),
        (
            "albumentations: cap below 2.0 to avoid breaking API changes",
            r"^albumentations[>=!<~^].*$",
            "albumentations>=1.4.16,<2.0.0",
            True
        ),
        (
            "onnx: raise floor to 1.18.0 (Python 3.13 wheels)",
            r"^onnx[>=!<~^].*$",
            "onnx>=1.18.0",
            True
        ),
        (
            "insightface: comment out (handled by ensure_insightface() in install.py)",
            r"^(insightface.*)$",
            r"# [py313-patch] \1  # installed via prebuilt wheel - see install.py",
            True
        ),
        (
            "importlib_metadata: comment out (now using stdlib)",
            r"^(importlib.metadata.*)$",
            r"# [py313-patch] \1  # removed - use stdlib importlib.metadata",
            True
        ),
    ]

    original = read_file(path)
    content = original
    changed = False

    for desc, old, new, use_regex in patches:
        if use_regex:
            new_content = re.sub(old, new, content, flags=re.MULTILINE)
        else:
            new_content = content.replace(old, new)
        if new_content != content:
            print(green(f"  ✔ {desc}"))
            content = new_content
            changed = True

    # Add packaging if not present
    if "packaging" not in content:
        content += "\npackaging>=21.0\n"
        print(green("  ✔ Added packaging>=21.0 (needed for version comparison)"))
        changed = True

    if changed:
        write_file(path, content, dry_run)
    else:
        print("  (no changes needed)")
    return changed


def patch_pyproject_toml(path, dry_run=False):
    print(bold(f"\n[pyproject.toml] {path}"))

    patches = [
        (
            "numpy: remove ==1.26.4 pin, replace with >=2.0.0",
            r'"numpy[>=!<~^=]+[^"]*"',
            '"numpy>=2.0.0"',
            True
        ),
        (
            "numpy single-quoted: remove ==1.26.4 pin, replace with >=2.0.0",
            r"'numpy[>=!<~^=]+[^']*'",
            "'numpy>=2.0.0'",
            True
        ),
        (
            "onnx: raise floor to 1.18.0",
            r'"onnx[>=!<~^=]+[^"]*"',
            '"onnx>=1.18.0"',
            True
        ),
        (
            "Remove importlib_metadata dependency",
            r'"importlib[_-]metadata[^"]*",?\s*\n?',
            "",
            True
        ),
        (
            "insightface: comment out pinned version (wheel managed separately)",
            r'("insightface[^"]*")',
            r'# [py313-patch] \1  # use prebuilt wheel',
            True
        ),
    ]

    original = read_file(path)
    content = original
    changed = False

    for desc, old, new, use_regex in patches:
        if use_regex:
            new_content = re.sub(old, new, content, flags=re.MULTILINE)
        else:
            new_content = content.replace(old, new)
        if new_content != content:
            print(green(f"  ✔ {desc}"))
            content = new_content
            changed = True

    # Add python_requires if missing
    if "python_requires" not in content and "[tool.setuptools]" not in content:
        # Try to insert after [project] header
        if "[project]" in content:
            content = content.replace(
                "[project]\n",
                '[project]\npython_requires = ">=3.10"\n'
            )
            print(green("  ✔ Added python_requires = '>=3.10'"))
            changed = True

    if changed:
        write_file(path, content, dry_run)
    else:
        print("  (no changes needed)")
    return changed


def patch_numpy_aliases(path, dry_run=False):
    """Fix deprecated numpy 2.x type aliases in any .py file."""
    NUMPY_ALIASES = [
        (r'\bnp\.bool\b(?!_)',    'np.bool_'),
        (r'\bnp\.int\b(?!_|8|16|32|64|p)',   'np.int_'),
        (r'\bnp\.float\b(?!_|16|32|64|128)', 'np.float64'),
        (r'\bnp\.complex\b(?!_|64|128)',      'np.complex128'),
        (r'\bnp\.object\b(?!_)',  'np.object_'),
        (r'\bnp\.str\b(?!_|ing)', 'np.str_'),
        (r'\bnp\.long\b',         'np.int_'),
        (r'\bnp\.unicode\b(?!_)', 'np.str_'),
        (r'\bnumpy\.bool\b(?!_)', 'numpy.bool_'),
        (r'\bnumpy\.int\b(?!_|8|16|32|64|p)', 'numpy.int_'),
        (r'\bnumpy\.float\b(?!_|16|32|64|128)', 'numpy.float64'),
        (r'\bnumpy\.complex\b(?!_|64|128)',     'numpy.complex128'),
        (r'\bnumpy\.object\b(?!_)', 'numpy.object_'),
        (r'\bnumpy\.str\b(?!_|ing)', 'numpy.str_'),
    ]

    original = read_file(path)
    content = original

    for pattern, replacement in NUMPY_ALIASES:
        content = re.sub(pattern, replacement, content)

    if content != original:
        rel = os.path.relpath(path)
        print(green(f"  ✔ Fixed NumPy 2.x aliases in {rel}"))
        write_file(path, content, dry_run)
        return True
    return False


def patch_distutils(path, dry_run=False):
    """Replace distutils (removed in Python 3.12) with packaging.version."""
    DISTUTILS_PATTERNS = [
        (
            r"from distutils\.version import LooseVersion",
            "from packaging.version import Version as LooseVersion"
        ),
        (
            r"from distutils\.version import StrictVersion",
            "from packaging.version import Version as StrictVersion"
        ),
        (
            r"import distutils\.version",
            "import packaging.version  # [py313-patch] distutils removed"
        ),
        (
            r"from distutils import version",
            "from packaging import version  # [py313-patch] distutils removed"
        ),
        (
            r"from distutils\.util import",
            "# [py313-patch] from distutils.util import"
        ),
        (
            r"from distutils\.core import",
            "# [py313-patch] from distutils.core import"
        ),
    ]

    original = read_file(path)
    content = original

    for pattern, replacement in DISTUTILS_PATTERNS:
        content = re.sub(pattern, replacement, content)

    if content != original:
        rel = os.path.relpath(path)
        print(green(f"  ✔ Replaced distutils imports in {rel}"))
        write_file(path, content, dry_run)
        return True
    return False


def patch_pkg_resources_generic(path, dry_run=False):
    """Replace any remaining pkg_resources usage across all .py files."""
    PATTERNS = [
        (
            r"^import pkg_resources\s*$",
            "# [py313-patch] import pkg_resources  # removed; use importlib.metadata\n"
            "import importlib.metadata as _imeta"
        ),
        (
            r"^from pkg_resources import (.+)$",
            r"# [py313-patch] from pkg_resources import \1  # removed; use importlib.metadata"
        ),
        (
            r"pkg_resources\.get_distribution\(([^)]+)\)\.version",
            r"importlib.metadata.version(\1)"
        ),
        (
            r"pkg_resources\.require\(",
            r"# [py313-patch] pkg_resources.require("
        ),
    ]

    original = read_file(path)
    content = original

    for pattern, replacement in PATTERNS:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if content != original:
        rel = os.path.relpath(path)
        print(green(f"  ✔ Replaced pkg_resources in {rel}"))
        write_file(path, content, dry_run)
        return True
    return False


# ── Directory scanner ────────────────────────────────────────────────────────

def find_repo_root(start=None):
    """Try to locate the ComfyUI-ReActor-NSFW directory."""
    if start:
        if os.path.isdir(start):
            return start
        print(red(f"Error: path not found: {start}"))
        sys.exit(1)

    # Check current directory
    cwd = os.getcwd()
    if os.path.basename(cwd).lower().startswith("comfyui-reactor"):
        return cwd

    # Check common ComfyUI paths
    candidates = [
        os.path.join(cwd, "ComfyUI-ReActor-NSFW"),
        os.path.join(cwd, "custom_nodes", "ComfyUI-ReActor-NSFW"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c

    # Walk upward looking for custom_nodes
    check = cwd
    for _ in range(4):
        candidate = os.path.join(check, "custom_nodes", "ComfyUI-ReActor-NSFW")
        if os.path.isdir(candidate):
            return candidate
        check = os.path.dirname(check)

    return None


def get_all_py_files(root):
    """Return all .py files under root, skipping .bak and __pycache__."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('__pycache__', '.git', 'node_modules')]
        for fn in filenames:
            if fn.endswith('.py') and not fn.endswith('.bak'):
                results.append(os.path.join(dirpath, fn))
    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Patch ComfyUI-ReActor-NSFW for Python 3.13 + NumPy 2.x"
    )
    parser.add_argument(
        "path", nargs="?", default=None,
        help="Path to ComfyUI-ReActor-NSFW directory (auto-detected if omitted)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing any files"
    )
    args = parser.parse_args()

    print(bold(cyan("\n==========================================")))
    print(bold(cyan("  ComfyUI-ReActor-NSFW  Python 3.13 Patch")))
    print(bold(cyan("==========================================\n")))

    root = find_repo_root(args.path)
    if not root:
        print(red("Could not find ComfyUI-ReActor-NSFW directory."))
        print("Please run from inside the repo folder, or pass the path as an argument:")
        print("  python reactor_py313_patch.py \"C:/path/to/ComfyUI-ReActor-NSFW\"")
        sys.exit(1)

    print(f"Repo root : {bold(root)}")
    print(f"Dry run   : {bold(str(args.dry_run))}\n")

    total_changed = 0

    # ── Patch specific known files ──────────────────────────────────────────

    install_py = os.path.join(root, "install.py")
    if os.path.exists(install_py):
        if patch_install_py(install_py, args.dry_run):
            total_changed += 1
    else:
        print(yellow("\n[install.py] Not found - skipping"))

    req_txt = os.path.join(root, "requirements.txt")
    if os.path.exists(req_txt):
        if patch_requirements_txt(req_txt, args.dry_run):
            total_changed += 1
    else:
        print(yellow("\n[requirements.txt] Not found - skipping"))

    pyproject = os.path.join(root, "pyproject.toml")
    if os.path.exists(pyproject):
        if patch_pyproject_toml(pyproject, args.dry_run):
            total_changed += 1
    else:
        print(yellow("\n[pyproject.toml] Not found - skipping"))

    # ── Sweep all .py files ─────────────────────────────────────────────────

    print(bold(cyan("\n── Scanning all .py files for NumPy aliases + distutils + pkg_resources ──")))

    all_py = get_all_py_files(root)
    print(f"Found {len(all_py)} Python files to scan...\n")

    numpy_fixed = 0
    distutils_fixed = 0
    pkgres_fixed = 0

    for pyfile in all_py:
        fn = os.path.basename(pyfile)
        if fn in ("reactor_py313_patch.py",):
            continue  # don't patch ourselves

        n = patch_numpy_aliases(pyfile, args.dry_run)
        d = patch_distutils(pyfile, args.dry_run)
        p = patch_pkg_resources_generic(pyfile, args.dry_run)

        if n: numpy_fixed += 1
        if d: distutils_fixed += 1
        if p: pkgres_fixed += 1
        total_changed += (1 if (n or d or p) else 0)

    # ── Summary ─────────────────────────────────────────────────────────────

    print(bold(cyan("\n══════════════════════════════════════════")))
    print(bold("  PATCH SUMMARY"))
    print(bold(cyan("══════════════════════════════════════════")))
    print(f"  Files modified       : {green(str(total_changed))}")
    print(f"  NumPy alias fixes    : {green(str(numpy_fixed))} files")
    print(f"  distutils removals   : {green(str(distutils_fixed))} files")
    print(f"  pkg_resources fixes  : {green(str(pkgres_fixed))} files")

    if args.dry_run:
        print(yellow("\n  [DRY-RUN] No files were written."))
    else:
        print(green("\n  All patches applied. Backups saved as .bak files."))
        print(cyan("  To revert any file: rename the .bak back to the original filename."))

    print(bold(cyan("\n══════════════════════════════════════════")))
    print(bold("\n  Next steps:"))
    print("  1. Revoke your GitHub token if you haven't already")
    print("  2. Install the insightface wheel manually if needed:")
    print(cyan("     pip install https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp313-cp313-win_amd64.whl"))
    print("  3. Install updated requirements:")
    print(cyan("     pip install -r requirements.txt"))
    print("  4. Restart ComfyUI\n")


if __name__ == "__main__":
    main()