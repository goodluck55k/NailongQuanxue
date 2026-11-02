"""校验 Windows 发行 ZIP 的结构与内容，确保解压即用且不含个人数据。

用法：
    python tools/verify_bundle.py dist/.../NailongQuanxue-v2.0.1-Windows-x64.zip --report out.json

退出码：0 通过；2 结构或内容不符合发行要求。
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = "NailongQuanxue/"
REQUIRED_FILES = [
    "NailongQuanxue.exe",
    "LICENSE",
    "README.md",
    "PRIVACY.md",
    "THIRD_PARTY_NOTICES.md",
    "ASSET_MANIFEST.md",

]
REQUIRED_DIRS = ["_internal/", "licenses/"]
REQUIRED_INTERNAL = [
    "_internal/assets/default_break.mp4",
    "_internal/assets/fallback_overlay.jpg",
]
FORBIDDEN_NAMES = {
    "settings.json", "pending-events.json", "location.txt", "environment.txt",
}
FORBIDDEN_SUFFIXES = (".sqlite3", ".sqlite", ".db", ".log", ".wav", ".mp3", ".flac",
                      ".m4a", ".tmp", ".pyc", ".pdb")
FORBIDDEN_PARTS = {"photos", "videos", "diagnostics", "NailongData", "__pycache__",
                   "crash", "logs"}


def normalise(name):
    return name.replace("\\", "/")


def check(zip_path, expect_release=True):
    report = {"zip": str(zip_path), "ok": False, "errors": [], "warnings": [], "stats": {}}
    errors = report["errors"]
    if not zip_path.is_file():
        errors.append("ZIP not found: %s" % zip_path)
        return report

    with zipfile.ZipFile(zip_path) as archive:
        names = [normalise(item) for item in archive.namelist()]
        infos = {normalise(item.filename): item for item in archive.infolist()}

        tops = {name.split("/")[0] for name in names if name}
        if tops != {"NailongQuanxue"}:
            errors.append("ZIP must contain a single top-level folder 'NailongQuanxue', found %s"
                          % sorted(tops))

        for name in names:
            if name.startswith("/") or ".." in name.split("/"):
                errors.append("unsafe path in ZIP: %s" % name)

        for relative in REQUIRED_FILES:
            if ROOT + relative not in names:
                errors.append("missing file: %s%s" % (ROOT, relative))
        for directory in REQUIRED_DIRS:
            if not any(name.startswith(ROOT + directory) for name in names):
                errors.append("missing folder: %s%s" % (ROOT, directory))
        for relative in REQUIRED_INTERNAL:
            if ROOT + relative not in names:
                errors.append("missing bundled asset: %s%s" % (ROOT, relative))

        bad = []
        for name in names:
            parts = name.split("/")
            base = parts[-1]
            if base in FORBIDDEN_NAMES:
                bad.append(name)
            elif base.lower().endswith(FORBIDDEN_SUFFIXES):
                bad.append(name)
            elif any(part.lower() in FORBIDDEN_PARTS for part in parts[1:-1]):
                bad.append(name)
        if expect_release and any(name.endswith("LOCAL-ONLY-NOT-PUBLISHED.txt") for name in names):
            bad.append("LOCAL-ONLY-NOT-PUBLISHED.txt present")
        if bad:
            errors.append("forbidden entries in ZIP: %s" % ", ".join(sorted(set(bad))[:10]))

        exe = ROOT + "NailongQuanxue.exe"
        if exe not in names:
            errors.append("missing executable: %s" % exe)
        else:
            size = infos[exe].file_size
            report["stats"]["exe_bytes"] = size
            if size < 200_000:
                errors.append("executable looks truncated: %d bytes" % size)

        internal = [name for name in names if name.startswith(ROOT + "_internal/")]
        report["stats"]["internal_files"] = len(internal)
        if len(internal) < 40:
            errors.append("_internal looks incomplete: %d files" % len(internal))

        assets = [name for name in names if name.startswith(ROOT + "assets/")]
        report["stats"]["asset_files"] = len(assets)
        report["stats"]["total_entries"] = len(names)
        report["stats"]["uncompressed_bytes"] = sum(info.file_size for info in infos.values())
        report["stats"]["zip_bytes"] = zip_path.stat().st_size

        for info in infos.values():
            if info.compress_size == 0 and info.file_size > 0:
                errors.append("entry stored without compression: %s" % info.filename)
                break

    report["ok"] = not errors
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify a NailongQuanxue release ZIP.")
    parser.add_argument("zip")
    parser.add_argument("--report", default=None)
    parser.add_argument("--allow-local-notice", action="store_true",
                        help="local builds may keep LOCAL-ONLY-NOT-PUBLISHED.txt")
    args = parser.parse_args(argv)
    report = check(Path(args.zip), expect_release=not args.allow_local_notice)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
