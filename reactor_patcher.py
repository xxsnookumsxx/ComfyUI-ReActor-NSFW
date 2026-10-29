import os
import glob
import insightface
from insightface.app.common import Face
from insightface.model_zoo import model_zoo

def patched_faceanalysis_init(self, name='buffalo_l', root='~/.insightface', allowed_modules=None, **kwargs):
    onnxruntime = kwargs.get('onnxruntime', None)
    if onnxruntime is not None:
        kwargs.pop('onnxruntime')
    self.models = {}
    self.root = os.path.expanduser(root)
    self.name = name
    self.model_dir = os.path.join(self.root, 'models', name)
    onnx_files = glob.glob(os.path.join(self.model_dir, '*.onnx'))
    onnx_files.sort()
    for onnx_file in onnx_files:
        try:
            model = model_zoo.get_model(onnx_file, **kwargs)
        except Exception as e:
            print(f"[ReActor] Warning: Failed to load model {onnx_file}: {e}")
            continue

        if model is None:
            print(f"[ReActor] Model not recognized: {onnx_file}")
            continue

        # Safe taskname resolution to prevent 'INSwapper' object has no attribute 'taskname'
        taskname = getattr(model, "taskname", getattr(model, "task", None))
        if not taskname:
            continue

        if taskname not in self.models and (allowed_modules is None or taskname in allowed_modules):
            self.models[taskname] = model

    # Fallback default sorting if det model exists
    if 'detection' in self.models:
        self.det_model = self.models['detection']
    else:
        self.det_model = None

def patch_insightface():
    """Apply the patched FaceAnalysis.__init__ to the active insightface library."""
    try:
        insightface.app.FaceAnalysis.__init__ = patched_faceanalysis_init
    except Exception as e:
        print(f"[ReActor] Failed to patch FaceAnalysis: {e}")

# Apply patch immediately on module load
patch_insightface()
