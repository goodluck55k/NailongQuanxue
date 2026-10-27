"""Package v1.1.0 using the accepted EXE/runtime without rebuilding it.

Only local files are written. This tool never calls GitHub or uploads data.
"""

import hashlib
import json
import marshal
from pathlib import Path
import shutil
import sys
import types
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PyInstaller.archive.readers import CArchiveReader
from tools.scan_public import Auditor

ACCEPTED_EXE_SHA = "ff26b87f64b9cd24bdd590a54c7552e0bdae4c6b9a798264244da29568e9303c"
ACCEPTED_ZIP_SHA = "917bcee19efaa601f1770d35765faf1ae98af82a3bea31514cc17c64166a6d8f"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(code):
    return code.replace(co_filename="<release>", co_consts=tuple(
        normalized(item) if isinstance(item, types.CodeType) else item for item in code.co_consts))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def prepare():
    accepted = ROOT / "dist/v1.1-local/NailongQuanxue"
    accepted_zip = ROOT / "dist/v1.1-local/NailongQuanxue-v1.1.0-Windows-local.zip"
    exe = accepted / "NailongQuanxue.exe"
    require(digest(exe.read_bytes()) == ACCEPTED_EXE_SHA, "Accepted EXE fingerprint changed")
    require(digest(accepted_zip.read_bytes()) == ACCEPTED_ZIP_SHA, "Accepted ZIP fingerprint changed")
    with zipfile.ZipFile(accepted_zip) as archive:
        original = {name.split("/", 1)[1]: digest(archive.read(name))
                    for name in archive.namelist() if not name.endswith("/")}
    current = {p.relative_to(accepted).as_posix(): digest(p.read_bytes())
               for p in accepted.rglob("*") if p.is_file()}
    require(current == original, "Accepted directory differs from accepted ZIP")

    reader = CArchiveReader(str(exe))
    pyz = reader.open_embedded_archive(next(name for name, toc in reader.toc.items() if toc[-1] == "z"))
    modules = 0
    for source in sorted((ROOT / "app").glob("*.py")):
        name = "app" if source.name == "__init__.py" else "app." + source.stem
        require(normalized(pyz.extract(name)) == normalized(compile(source.read_bytes(), str(source), "exec")),
                f"Application source differs from accepted EXE: {name}")
        modules += 1
    require(normalized(marshal.loads(reader.extract("main"))) == normalized(
        compile((ROOT / "main.py").read_bytes(), "main.py", "exec")), "Main differs from accepted EXE")

    auditor = Auditor(allow_fixed_assets=True)
    source_names = auditor.source_manifest(ROOT, ROOT / "PUBLIC_FILES.txt")
    auditor.scan(accepted)
    output = ROOT / "dist/v1.1.0"
    bundle = output / "NailongQuanxue"
    bundle.mkdir(parents=True, exist_ok=True)
    require(not any(bundle.iterdir()), "Formal bundle already exists; choose a fresh output directory")
    runtime = {name: sha for name, sha in current.items()
               if name == "NailongQuanxue.exe" or name.startswith("_internal/")}
    for name in runtime:
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(accepted / name, target)
    for name in ("README.md", "README-Windows.md", "LICENSE", "PRIVACY.md", "THIRD_PARTY_NOTICES.md",
                 "MANUAL_TESTS.md", "TEST_REPORT.md", "RELEASE_NOTES.md"):
        shutil.copyfile(ROOT / name, bundle / name)
    shutil.copyfile(ROOT / "assets/ASSET_MANIFEST.md", bundle / "ASSET_MANIFEST.md")
    shutil.copytree(ROOT / "licenses", bundle / "licenses")
    require(all(digest((bundle / name).read_bytes()) == sha for name, sha in runtime.items()),
            "Runtime changed during formal packaging")
    auditor.scan(bundle)
    windows_zip = output / "NailongQuanxue-v1.1.0-Windows-x64.zip"
    with zipfile.ZipFile(windows_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output).as_posix())
    with zipfile.ZipFile(windows_zip) as archive:
        require(all(digest(archive.read("NailongQuanxue/" + name)) == sha for name, sha in runtime.items()),
                "ZIP runtime differs from accepted runtime")
    auditor.scan(windows_zip)
    for name in ("README-Windows.md", "RELEASE_NOTES.md", "PUBLIC_FILES.txt"):
        shutil.copyfile(ROOT / name, output / name)
    shutil.copyfile(exe, output / exe.name)
    report = auditor.report() | {
        "version": "1.1.0", "application_recompiled": False,
        "source_modules_match_accepted_exe": modules + 1,
        "unchanged_runtime_files": len(runtime), "source_file_count": len(source_names),
        "accepted_exe_sha256": ACCEPTED_EXE_SHA, "accepted_zip_sha256": ACCEPTED_ZIP_SHA,
        "windows_zip_sha256": digest(windows_zip.read_bytes()),
        "windows_zip_bytes": windows_zip.stat().st_size,
        "runtime_bytes_identical_to_accepted": True,
        "packaging_changes": "release documentation and ZIP container only"
    }
    report_path = ROOT / "build/publish-v110-package.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    prepare()
