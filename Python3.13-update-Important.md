Hi all,
If you are on the latest version of comfyui using python 3.13.12 and finding that the repo is broke, I used claude sonnet 4.6 thinking to rebuild this extension to compile insightface from source and check for errors.

When I used the 3.13 whl from original repo it was installing for python 3.12 not 3.13 and started to cause errors.

Also, had claude update numpy so it now uses version 2+ so it not break other extensions from installing numpy 1.

any issues let me know and I'll try do another update with a how to guide or something.

Couple of notes:

File 01: reactor_py313_patch.py
This is the original patch file I used to change most of the code before I realised there was a python mismatch error going on.

File 02: reactor_insightface_fix.py
This fix updated the install to do the python error checks and install from source for 3.13.

So this version is effectivly for python 3.13 only till at such time comfyui updates to 3.14 and then I'll make a new version for it.

PS: The .bak files are from the original repo I forked in case you need to put everything back to normal.
