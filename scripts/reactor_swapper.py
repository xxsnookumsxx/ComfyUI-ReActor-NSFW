import os
import sys
import glob
import numpy as np
import insightface
from insightface.app import FaceAnalysis

# Add parent directory to path so reactor_patcher can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import reactor_patcher
    reactor_patcher.patch_insightface()
except Exception as e:
    print(f"[ReActor] Patcher warning: {e}")
