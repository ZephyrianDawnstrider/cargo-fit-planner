"""Create the allowlisted, database-free runtime directory used by Render."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".render-runtime"
MARKER = ".cargo-fit-planner-generated"
MARKER_CONTENT = "Cargo Fit Planner allowlisted runtime v1\n"
ALLOWLIST = (
    "dcd_project/__init__.py",
    "dcd_project/settings_render.py",
    "dcd_project/urls_render.py",
    "dcd_project/wsgi_render.py",
    "optimization/__init__.py",
    "optimization/admission.py",
    "optimization/mvp_views.py",
    "optimization/packing.py",
    "optimization/templates/optimization/mvp.html",
)


def build_runtime() -> list[str]:
    if TARGET.exists() or TARGET.is_symlink():
        if TARGET.is_symlink() or not TARGET.is_dir():
            raise RuntimeError("Refusing to replace a non-directory runtime target")
        marker = TARGET / MARKER
        if not marker.is_file() or marker.read_text(encoding="utf-8") != MARKER_CONTENT:
            raise RuntimeError("Refusing to replace an unrecognized .render-runtime directory")
        shutil.rmtree(TARGET)

    copied = []
    for relative in ALLOWLIST:
        source = (ROOT / relative).resolve()
        if not source.is_relative_to(ROOT) or not source.is_file() or (ROOT / relative).is_symlink():
            raise RuntimeError(f"Missing or unsafe runtime input: {relative}")
        destination = TARGET / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied.append(relative)
    (TARGET / MARKER).write_text(MARKER_CONTENT, encoding="utf-8")
    return copied


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != ".render-runtime":
        raise SystemExit("The only supported output path is .render-runtime")
    for path in build_runtime():
        print(path)
    print(f"staged {len(ALLOWLIST)} allowlisted files under .render-runtime")
