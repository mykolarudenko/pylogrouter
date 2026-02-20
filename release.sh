#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f pyproject.toml ]]; then
  echo "ERROR: pyproject.toml not found. Run release.sh from project root."
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: Working tree is not clean. Commit or stash all changes before release."
  exit 1
fi

mapfile -t version_data < <(uv run python - <<'PY'
import pathlib
import re
import tomllib

pyproject_path = pathlib.Path("pyproject.toml")
version_py_path = pathlib.Path("src/pylogrouter/version.py")

project_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
current = project_data["project"]["version"]

match = re.search(
    r'__version__\s*=\s*"(?P<version>\d+\.\d+\.\d+)"',
    version_py_path.read_text(encoding="utf-8"),
)
if match is None:
    raise SystemExit("ERROR: Could not parse __version__ in src/pylogrouter/version.py")

version_py = match.group("version")
if current != version_py:
    raise SystemExit(
        f"ERROR: Version mismatch. pyproject={current}, version.py={version_py}"
    )

parts = current.split(".")
if len(parts) != 3 or not all(item.isdigit() for item in parts):
    raise SystemExit(f"ERROR: Unsupported version format '{current}'. Expected X.Y.Z")

major, minor, patch = map(int, parts)
next_version = f"{major}.{minor}.{patch + 1}"
print(current)
print(next_version)
PY
)

CURRENT_VERSION="${version_data[0]}"
NEXT_VERSION="${version_data[1]}"

echo "Releasing: ${CURRENT_VERSION} -> ${NEXT_VERSION}"

NEXT_VERSION="$NEXT_VERSION" uv run python - <<'PY'
import os
import pathlib
import re

next_version = os.environ["NEXT_VERSION"]

pyproject_path = pathlib.Path("pyproject.toml")
pyproject_text = pyproject_path.read_text(encoding="utf-8")
updated_pyproject = re.sub(
    r'(?m)^version\s*=\s*"\d+\.\d+\.\d+"\s*$',
    f'version = "{next_version}"',
    pyproject_text,
    count=1,
)
if updated_pyproject == pyproject_text:
    raise SystemExit("ERROR: Failed to update version in pyproject.toml")
pyproject_path.write_text(updated_pyproject, encoding="utf-8")

version_py_path = pathlib.Path("src/pylogrouter/version.py")
version_py_text = version_py_path.read_text(encoding="utf-8")
updated_version_py = re.sub(
    r'(?m)^__version__\s*=\s*"\d+\.\d+\.\d+"\s*$',
    f'__version__ = "{next_version}"',
    version_py_text,
    count=1,
)
if updated_version_py == version_py_text:
    raise SystemExit("ERROR: Failed to update __version__ in src/pylogrouter/version.py")
version_py_path.write_text(updated_version_py, encoding="utf-8")
PY

uv lock
uv run --group dev pytest -q
uv build

uv run python - <<'PY'
import pathlib
import tarfile
import zipfile

dist_dir = pathlib.Path("dist")
wheel_path = sorted(dist_dir.glob("pylogrouter-*.whl"))[-1]
sdist_path = sorted(dist_dir.glob("pylogrouter-*.tar.gz"))[-1]

required = "pylogrouter/templates/log_document.html"
sdist_root = sdist_path.name[:-7]
required_sdist = f"{sdist_root}/src/{required}"
required_license = f"{sdist_root}/LICENSE"

with zipfile.ZipFile(wheel_path) as wheel:
    if required not in wheel.namelist():
        raise SystemExit(f"ERROR: {required} is missing in wheel")

with tarfile.open(sdist_path) as sdist:
    names = sdist.getnames()
    if required_sdist not in names:
        raise SystemExit(f"ERROR: {required} is missing in sdist")
    if required_license not in names:
        raise SystemExit("ERROR: LICENSE is missing in sdist")
PY

git add pyproject.toml src/pylogrouter/version.py uv.lock
git commit -m "Release v${NEXT_VERSION}"
git tag "v${NEXT_VERSION}"

git push
git push --tags

echo "Release prepared successfully."
echo "Release pushed successfully (branch + tags)."
