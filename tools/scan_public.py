"""Fail-closed local audit of an explicit source list, onedir bundle or ZIP.

The EXE check decompresses PyInstaller CArchive/PYZ members. It does not treat
an absence of loose image files as proof that embedded resources are safe.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

PRIVATE_SHA = "0cdd2f63eb0f9e4dc1fe8b5b880dbb54c6a53edc137bfdd6f9704746e7fa3f11"
FIXED_ASSETS = {"default_break.mp4": "98a2addcaeef70f58bdc7f36740b813a97cd021fc37141a8c0e53e4407fa6c4c",
                "fallback_overlay.jpg": PRIVATE_SHA,
                "ui_reference.png": "eeb99288c797822f99e7dc96e9d9f8c55a09fbc8bac3e1bde2272a281a6c5831"}
TEXT_SUFFIXES = {".py", ".ps1", ".md", ".txt", ".ini", ".yml", ".json", ".toml"}


class AuditError(RuntimeError):
    pass


class Auditor:
    def __init__(self, private_image: Path | None = None, allow_fixed_assets=False):
        self.private_bytes = private_image.read_bytes() if private_image and private_image.is_file() else None
        self.allow_fixed_assets = allow_fixed_assets
        self.checked = 0
        self.archives = 0
        self.executables = 0

    def check_name(self, name: str):
        parts = PurePosixPath(name.replace("\\", "/")).parts
        lowered = [part.lower() for part in parts]
        if ".." in parts or (parts and (parts[0] == "/" or ":" in parts[0])):
            raise AuditError(f"Unsafe archive path: {name}")
        if any(part in {".env", ".venv", ".git", "__pycache__"} for part in lowered):
            raise AuditError(f"Private/cache entry: {name}")
        if any(part in {"photos", "settings.json", "pending-events.json"} or part.endswith((".sqlite3", ".sqlite", ".db", ".log")) for part in lowered):
            raise AuditError(f"Personal application data: {name}")
        if any(part in {"overlay.jpg", "overlay.jpeg", "overlay.png"} for part in lowered):
            raise AuditError(f"Local image entry: {name}")
        if any(part.startswith("screenbreaklocal") or part.startswith("screenbreakprivate") for part in lowered):
            raise AuditError(f"Private build entry: {name}")

    def fixed_asset(self, name, data):
        parts = PurePosixPath(name.replace("\\", "/").split("!")[-1]).parts
        return bool(self.allow_fixed_assets and len(parts) >= 2 and parts[-2] == "assets"
                    and parts[-1] in FIXED_ASSETS
                    and hashlib.sha256(data).hexdigest() == FIXED_ASSETS[parts[-1]])

    def check_bytes(self, name: str, data: bytes, text=False, fixed=False):
        self.checked += 1
        if not fixed and hashlib.sha256(data).hexdigest() == PRIVATE_SHA:
            raise AuditError(f"Private image fingerprint: {name}")
        if not fixed and self.private_bytes and self.private_bytes in data:
            raise AuditError(f"Private image bytes: {name}")
        if text:
            # Construct expressions to avoid matching these expressions themselves.
            absolute_path = rb"[A-Za-z]" + rb":[\\/]Users[\\/][^\s\x00]+"
            token = rb"(?:gh[pousr]_" + rb"[A-Za-z0-9]{30,}|github_pat_" + rb"[A-Za-z0-9_]{40,}|sk-" + rb"[A-Za-z0-9]{32,})"
            key = b"-----BEGIN " + b"(?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
            if any(re.search(pattern, data, re.IGNORECASE) for pattern in (absolute_path, token, key)):
                raise AuditError(f"Personal path or secret pattern: {name}")

    def _check_zip(self, name: str, data: bytes, depth: int):
        self.archives += 1
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                self.check_name(entry.filename)
                if not entry.is_dir():
                    self.check_entry(f"{name}!{entry.filename}", archive.read(entry), depth + 1)

    def _check_exe(self, name: str, data: bytes):
        from PyInstaller.archive.readers import CArchiveReader

        self.executables += 1
        # Inspection only: the copied executable is never run.
        with tempfile.TemporaryDirectory(prefix="screenbreak-audit-") as folder:
            path = Path(folder) / "inspect.exe"
            path.write_bytes(data)
            try:
                archive = CArchiveReader(str(path))
                self.archives += 1
                for member, toc in archive.toc.items():
                    self.check_name(member)
                    data = archive.extract(member)
                    self.check_bytes(f"{name}!{member}", data, text=True,
                                     fixed=self.fixed_asset(member, data))
                    if toc[-1] == "z":
                        pyz = archive.open_embedded_archive(member)
                        self.archives += 1
                        for module in pyz.toc:
                            content = pyz.extract(module, raw=True)
                            if content is not None:
                                self.check_bytes(f"{name}!{module}", content, text=True)
            except AuditError:
                raise
            except Exception as error:
                raise AuditError(f"Cannot inspect executable: {name} ({type(error).__name__})") from error

    def check_entry(self, name: str, data: bytes, depth: int = 0):
        if depth > 5:
            raise AuditError("Archive nesting limit exceeded")
        self.check_name(name.split("!")[-1])
        suffix = PurePosixPath(name).suffix.lower()
        if self.allow_fixed_assets and suffix in {".jpg", ".jpeg", ".png", ".mp4"} and not self.fixed_asset(name, data):
            raise AuditError(f"Undeclared image/video (possible personal capture): {name}")
        if self.allow_fixed_assets and PurePosixPath(name).name in FIXED_ASSETS and not self.fixed_asset(name, data):
            raise AuditError(f"Fixed asset path or fingerprint mismatch: {name}")
        self.check_bytes(name, data, text=suffix in TEXT_SUFFIXES or suffix == ".exe",
                         fixed=self.fixed_asset(name, data))
        if suffix == ".zip":
            self._check_zip(name, data, depth)
        elif suffix == ".exe":
            self._check_exe(name, data)

    def scan(self, path: Path):
        if not path.exists():
            raise AuditError(f"Missing input: {path.name}")
        if path.is_dir():
            files = sorted(item for item in path.rglob("*") if item.is_file())
            if not files:
                raise AuditError("Empty bundle")
            for file in files:
                if file.is_symlink():
                    raise AuditError("Symlinks are not allowed")
                self.check_entry(file.relative_to(path).as_posix(), file.read_bytes())
        else:
            self.check_entry(path.name, path.read_bytes())

    def source_manifest(self, root: Path, manifest: Path):
        names = [line.strip() for line in manifest.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]
        if not names or len(names) != len(set(names)):
            raise AuditError("Source manifest is empty or has duplicates")
        for name in names:
            self.check_name(name)
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
                raise AuditError(f"Missing or unsafe source file: {name}")
            self.check_entry(name, path.read_bytes())
        return names

    def report(self):
        return {"result": "PASS", "checked_entries": self.checked,
                "inspected_archives": self.archives, "inspected_executables": self.executables,
                "private_image_fingerprint": "only_declared_local_fixed_assets_allowed" if self.allow_fixed_assets else "absent",
                "local_asset_filenames": "declared_V1.1_assets_only" if self.allow_fixed_assets else "absent",
                "publication_authorized": False,
                "scope": "known image bytes/hash, resource names, secret patterns, personal user paths"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?")
    parser.add_argument("--sources", type=Path, help="Project root with PUBLIC_FILES.txt")
    parser.add_argument("--private-image", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--allow-fixed-assets", action="store_true", help="Local V1.1 candidate only; not redistribution approval")
    args = parser.parse_args()
    if (args.path is None) == (args.sources is None):
        parser.error("Provide exactly one bundle path or --sources")
    auditor = Auditor(args.private_image, allow_fixed_assets=args.allow_fixed_assets)
    try:
        if args.sources:
            auditor.source_manifest(args.sources, args.sources / "PUBLIC_FILES.txt")
        else:
            auditor.scan(args.path)
        report = auditor.report()
    except (AuditError, OSError, zipfile.BadZipFile) as error:
        print(f"FAIL: {error}")
        return 1
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
