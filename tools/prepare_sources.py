"""Export only the reviewed source manifest to a local ZIP. No GitHub calls."""

import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.scan_public import Auditor


def main():
    auditor = Auditor(allow_fixed_assets=True)
    names = auditor.source_manifest(ROOT, ROOT / "PUBLIC_FILES.txt")
    target = ROOT / "dist" / "v1.1-local" / "NailongQuanxue-v1.1.0-source-local.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(ROOT / name, "NailongQuanxue/" + name)
    auditor.scan(target)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{checksum}  {target.name}\n", encoding="ascii")
    report = auditor.report() | {"source_file_count": len(names), "sha256": checksum}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "source-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
