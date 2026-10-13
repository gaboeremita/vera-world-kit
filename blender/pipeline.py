"""Builds, lights and exports a region in the open Blender file, logging to <region>/pipeline.log.

Run in Blender with KIT set to this folder and REGION to the region's content folder:
    exec(open(KIT + "/pipeline.py").read(), {"KIT": KIT, "REGION": REGION})

The region folder holds a `region.py` config module (see look.run and export.run for what they read)
whose BUILD lists the region's own scripts, run in order before the look and the export.
STEPS can limit the run to some of "build", "look" and "export"."""
import contextlib
import importlib
import io
import logging
import os
import sys
import time
import traceback

for folder in (REGION, KIT):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import region

importlib.reload(region)
import look
import export

importlib.reload(look)
importlib.reload(export)

steps = globals().get("STEPS", ("build", "look", "export"))
started = time.time()
lines = []


def build():
    for script in region.BUILD:
        exec(open(os.path.join(REGION, script)).read(), {"__name__": "__main__"})


for name, step in (("build", build), ("look", lambda: look.run(region)), ("export", lambda: export.run(region))):
    if name not in steps:
        continue
    buffer = io.StringIO()
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(buffer):
            step()
        lines.append(f"{name}: ok {buffer.getvalue().strip().splitlines()[-1:]}")
    except Exception:
        lines.append(f"{name}: FAILED\n{traceback.format_exc()[-2000:]}")
        break
    finally:
        logging.disable(logging.NOTSET)
lines.append(f"{time.time() - started:.0f}s")
open(os.path.join(REGION, "pipeline.log"), "w").write("\n".join(lines))
print("\n".join(lines))
