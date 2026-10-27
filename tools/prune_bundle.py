"""Remove unused image-format/SVG/software-GL dependencies from onedir output.

ScreenBreak paints raster widgets and reads JPEG, so it does not need TIFF,
WebP, SVG or Mesa software OpenGL. Qt's built-in PNG handling remains available.
"""

from pathlib import Path
import sys


def prune(bundle: Path):
    bundle = bundle.resolve()
    if not bundle.is_dir():
        raise FileNotFoundError(bundle)
    root = Path(__file__).resolve().parents[1] / "dist"
    if bundle.name not in {"ScreenBreak", "ScreenBreakLocal", "NailongQuanxue"} or not bundle.is_relative_to(root.resolve()):
        raise ValueError("Expected a ScreenBreak bundle inside this project's dist folder")
    for parent in (bundle, *bundle.parents):
        if parent == root.parent:
            break
        if getattr(parent.stat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("Reparse points are not allowed in build output")
    qt = bundle / "_internal" / "PySide6"
    candidates = [qt / "opengl32sw.dll", qt / "Qt6Svg.dll"]
    candidates += list((qt / "plugins" / "iconengines").glob("*.dll"))
    candidates += [file for file in (qt / "plugins" / "imageformats").glob("*.dll")
                   if file.name.lower() != "qjpeg.dll"]
    for file in candidates:
        if not file.resolve().is_relative_to(bundle):
            raise ValueError("File outside bundle")
        file.unlink(missing_ok=True)
    print("Removed unused SVG, extra image plugins and software OpenGL; JPEG retained")


if __name__ == "__main__":
    prune(Path(sys.argv[1]))
