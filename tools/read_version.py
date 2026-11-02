"""打印 main.py 中的 APP_VERSION，供构建脚本与 CI 使用（不导入 Qt）。"""
import argparse
import re
import sys
from pathlib import Path

PATTERN = re.compile(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def read_version(path=None):
    source = Path(path or Path(__file__).resolve().parent.parent / "main.py")
    match = PATTERN.search(source.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("APP_VERSION not found in %s" % source)
    return match.group(1).strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print the application version.")
    parser.add_argument("--check", metavar="EXPECTED", default=None,
                        help="exit 3 when the version differs from EXPECTED")
    parser.add_argument("--source", default=None, help="path to main.py")
    args = parser.parse_args(argv)
    version = read_version(args.source)
    print(version)
    if args.check is not None and args.check.strip().lstrip("vV") != version:
        print("version mismatch: expected %s, found %s" % (args.check, version), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
