#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/cut-release.sh --bump <major|minor|patch> [options]
  scripts/cut-release.sh --version <version> [options]

Required:
  --bump          Bump type (major, minor, patch)
  or
  --version       Release version (e.g., 1.2.3 or v1.2.3)

Options:
  --title         Release title (default: v<version>)
  --notes-file    Path to release notes markdown (optional; auto-generated from git log if omitted)
  --repo          GitHub repo (owner/name). Auto-detected from origin if omitted.
  --prerelease    Mark GitHub release as prerelease
  --update-versions  Update version fields and commit before tagging (default: true when using --bump)
  --no-update-versions  Do not update versions even if --bump is used
  --skip-gh       Skip GitHub release creation (tags and tarball only)
  --no-push       Do not push to origin (tags and tarball only)

Release notes must include:
  ## What's New
  ## Bug Fixes
  ## Breaking Changes
USAGE
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: Required command '$1' not found." >&2
    exit 1
  fi
}

bump=""
version=""
notes_file=""
title=""
repo=""
prerelease=false
update_versions=false
no_update_versions=false
skip_gh=false
no_push=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      version="$2"
      shift 2
      ;;
    --bump)
      bump="$2"
      shift 2
      ;;
    --notes-file)
      notes_file="$2"
      shift 2
      ;;
    --title)
      title="$2"
      shift 2
      ;;
    --repo)
      repo="$2"
      shift 2
      ;;
    --prerelease)
      prerelease=true
      shift
      ;;
    --update-versions)
      update_versions=true
      shift
      ;;
    --no-update-versions)
      no_update_versions=true
      shift
      ;;
    --skip-gh)
      skip_gh=true
      shift
      ;;
    --no-push)
      no_push=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
 done

if [[ -z "$version" && -z "$bump" ]]; then
  usage
  exit 1
fi

if [[ -n "$version" && -n "$bump" ]]; then
  echo "Error: Use either --version or --bump, not both." >&2
  exit 1
fi

if [[ -n "$bump" ]]; then
  if [[ "$bump" != "major" && "$bump" != "minor" && "$bump" != "patch" ]]; then
    echo "Error: --bump must be one of major, minor, patch." >&2
    exit 1
  fi
  if [[ "$no_update_versions" == "false" ]]; then
    update_versions=true
  fi
fi

version="${version#v}"

require_cmd git
require_cmd python3
if [[ "$skip_gh" == "false" ]]; then
  require_cmd gh
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: Not inside a git repository." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: Working tree is dirty. Commit or stash changes before releasing." >&2
  exit 1
fi

branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  echo "Error: Releases must be cut from main (current: $branch)." >&2
  exit 1
fi

git fetch origin --tags >/dev/null 2>&1

local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse origin/main)"
if [[ "$local_head" != "$remote_head" ]]; then
  if git merge-base --is-ancestor "$local_head" "origin/main"; then
    echo "Error: Local main is behind origin/main. Pull first." >&2
    exit 1
  fi
fi

get_latest_version() {
  python3 - <<'PY'
import re
import subprocess

tags = subprocess.check_output(["git", "tag", "--list", "v*", "--sort=-v:refname"], text=True).splitlines()

def normalize(tag: str) -> str:
    return tag.lstrip("v")

def is_stable(version: str) -> bool:
    return "-" not in version

versions = [normalize(t) for t in tags if t.strip()]
stable = [v for v in versions if is_stable(v)]

def pick_latest(items):
    return items[0] if items else ""

print(pick_latest(stable) or pick_latest(versions))
PY
}

bump_version() {
  python3 - <<PY
import re
import sys

current = "${1}"
bump = "${2}"

if not current:
    sys.exit("No existing tags found to bump from.")

m = re.match(r"^(\\d+)\\.(\\d+)\\.(\\d+)", current)
if not m:
    sys.exit(f"Latest version '{current}' is not semver-like.")

major, minor, patch = map(int, m.groups())
if bump == "major":
    major += 1
    minor = 0
    patch = 0
elif bump == "minor":
    minor += 1
    patch = 0
elif bump == "patch":
    patch += 1
else:
    sys.exit(f"Unsupported bump: {bump}")

print(f"{major}.{minor}.{patch}")
PY
}

if [[ -n "$bump" ]]; then
  latest_version="$(get_latest_version)"
  if [[ -z "$latest_version" ]]; then
    echo "Error: No existing tags found to bump from." >&2
    exit 1
  fi
  version="$(bump_version "$latest_version" "$bump")"
fi

if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
  echo "Error: Version must be semver-like (e.g., 1.2.3 or 1.2.3-beta.1)." >&2
  exit 1
fi

tag="v${version}"
if [[ -z "$title" ]]; then
  title="$tag"
fi

if git rev-parse "$tag" >/dev/null 2>&1; then
  echo "Error: Tag $tag already exists locally." >&2
  exit 1
fi
if git ls-remote --tags origin "$tag" | grep -q "$tag"; then
  echo "Error: Tag $tag already exists on origin." >&2
  exit 1
fi

ensure_notes_format() {
  local file="$1"
  for heading in "## What's New" "## Bug Fixes" "## Breaking Changes"; do
    if ! rg -q --fixed-strings "$heading" "$file" 2>/dev/null; then
      if ! grep -qF "$heading" "$file"; then
        echo "Error: Release notes missing required heading: $heading" >&2
        exit 1
      fi
    fi
  done
}

generate_notes() {
  local previous_tag="$1"
  local output="$2"

  {
    echo "## What's New"
    if [[ -n "$previous_tag" ]]; then
      git log "${previous_tag}..HEAD" --pretty=format:"- %s" | sed '/^$/d' | grep -v -E '^- Release v[0-9]' || true
    else
      git log --pretty=format:"- %s" | sed '/^$/d' | grep -v -E '^- Release v[0-9]' || true
    fi
    echo ""
    echo "## Bug Fixes"
    echo "- None"
    echo ""
    echo "## Breaking Changes"
    echo "- None"
    echo ""
    echo "## Upgrade Notes"
    echo "- None"
  } > "$output"
}

if [[ -n "$notes_file" ]]; then
  if [[ ! -f "$notes_file" ]]; then
    echo "Error: Release notes file not found: $notes_file" >&2
    exit 1
  fi
  ensure_notes_format "$notes_file"
fi

previous_tag="$(git tag --list 'v*' --sort=-v:refname | sed -n '1p')"
if [[ -z "$notes_file" ]]; then
  tmp_notes_dir="$(mktemp -d)"
  notes_tmp="$tmp_notes_dir/release-notes.md"
  generate_notes "$previous_tag" "$notes_tmp"
  notes_file="$notes_tmp"
  ensure_notes_format "$notes_file"
fi

read_versions() {
  python3 - <<'PY'
import json
import re
from pathlib import Path

root = Path('.')

# pyproject.toml
pyproject = root / 'daemon' / 'pyproject.toml'
version_py = None
if pyproject.exists():
    text = pyproject.read_text()
    m = re.search(r"^version\s*=\s*\"([^\"]+)\"", text, re.MULTILINE)
    if m:
        version_py = m.group(1)

# package.json / package-lock.json
pkg = root / 'frontend' / 'package.json'
version_pkg = None
if pkg.exists():
    version_pkg = json.loads(pkg.read_text()).get('version')

pkg_lock = root / 'frontend' / 'package-lock.json'
version_lock = None
if pkg_lock.exists():
    version_lock = json.loads(pkg_lock.read_text()).get('version')

# tau __init__ version
init_py = root / 'daemon' / 'src' / 'tau' / '__init__.py'
version_init = None
if init_py.exists():
    text = init_py.read_text()
    m = re.search(r"__version__\s*=\s*\"([^\"]+)\"", text)
    if m:
        version_init = m.group(1)

# tau main version (literal only)
main_py = root / 'daemon' / 'src' / 'tau' / 'main.py'
version_main = None
if main_py.exists():
    text = main_py.read_text()
    m = re.search(r"tau_daemon_starting\",\s*version=\"([^\"]+)\"", text)
    if m:
        version_main = m.group(1)

print("|".join([str(v or "") for v in [version_py, version_pkg, version_lock, version_init, version_main]]))
PY
}

versions_line="$(read_versions)"
IFS='|' read -r ver_py ver_pkg ver_lock ver_init ver_main <<< "$versions_line"

mismatches=()
[[ -n "$ver_py" && "$ver_py" != "$version" ]] && mismatches+=("daemon/pyproject.toml ($ver_py)")
[[ -n "$ver_pkg" && "$ver_pkg" != "$version" ]] && mismatches+=("frontend/package.json ($ver_pkg)")
[[ -n "$ver_lock" && "$ver_lock" != "$version" ]] && mismatches+=("frontend/package-lock.json ($ver_lock)")
[[ -n "$ver_init" && "$ver_init" != "$version" ]] && mismatches+=("daemon/src/tau/__init__.py ($ver_init)")
[[ -n "$ver_main" && "$ver_main" != "$version" ]] && mismatches+=("daemon/src/tau/main.py ($ver_main)")

if [[ ${#mismatches[@]} -gt 0 ]]; then
  if [[ "$update_versions" == "false" ]]; then
    echo "Error: Version mismatch. Update versions or rerun with --update-versions." >&2
    printf ' - %s\n' "${mismatches[@]}" >&2
    exit 1
  fi

  python3 - <<PY
import json
import re
from pathlib import Path

version = "${version}"

# pyproject.toml
pyproject = Path('daemon/pyproject.toml')
if pyproject.exists():
    text = pyproject.read_text()
    text = re.sub(r"^version\s*=\s*\"[^\"]+\"", f"version = \"{version}\"", text, flags=re.MULTILINE)
    pyproject.write_text(text)

# package.json
pkg = Path('frontend/package.json')
if pkg.exists():
    data = json.loads(pkg.read_text())
    data['version'] = version
    pkg.write_text(json.dumps(data, indent=2) + "\n")

# package-lock.json
pkg_lock = Path('frontend/package-lock.json')
if pkg_lock.exists():
    data = json.loads(pkg_lock.read_text())
    data['version'] = version
    pkg_lock.write_text(json.dumps(data, indent=2) + "\n")

# tau __init__
init_py = Path('daemon/src/tau/__init__.py')
if init_py.exists():
    text = init_py.read_text()
    text = re.sub(r"__version__\s*=\s*\"[^\"]+\"", f"__version__ = \"{version}\"", text)
    init_py.write_text(text)

# tau main (literal)
main_py = Path('daemon/src/tau/main.py')
if main_py.exists():
    text = main_py.read_text()
    text = re.sub(
        r"tau_daemon_starting\",\s*version=\"[^\"]+\"",
        f"tau_daemon_starting\", version=\"{version}\"",
        text,
    )
    main_py.write_text(text)
PY

  add_paths=(
    daemon/pyproject.toml
    frontend/package.json
    frontend/package-lock.json
    daemon/src/tau/__init__.py
    daemon/src/tau/main.py
  )
  for path in "${add_paths[@]}"; do
    if [[ -f "$path" ]]; then
      git add "$path"
    fi
  done
  git commit -m "Release $tag"
fi

# Tag
git tag -a "$tag" -m "$title"

if [[ "$no_push" == "false" ]]; then
  git push origin main
  git push origin "$tag"
fi

# Create tarball
tmpdir="$(mktemp -d)"
tarball="$tmpdir/tau-${tag}.tar.gz"
git archive --format=tar.gz --prefix=tau/ -o "$tarball" "$tag"

# Compute checksum
if command -v sha256sum >/dev/null 2>&1; then
  checksum="$(sha256sum "$tarball" | awk '{print $1}')"
else
  checksum="$(shasum -a 256 "$tarball" | awk '{print $1}')"
fi

notes_tmp="$tmpdir/release-notes.md"
cat "$notes_file" > "$notes_tmp"
{
  printf "\n\n## Checksums\n"
  printf "SHA256: %s\n" "$checksum"
} >> "$notes_tmp"

if [[ "$skip_gh" == "false" ]]; then
  if [[ -z "$repo" ]]; then
    remote_url="$(git remote get-url origin)"
    if [[ "$remote_url" =~ github.com[:/](.+/[^/.]+)(\.git)?$ ]]; then
      repo="${BASH_REMATCH[1]}"
    else
      echo "Error: Could not detect GitHub repo from origin. Use --repo owner/name." >&2
      exit 1
    fi
  fi

  gh auth status -h github.com >/dev/null 2>&1 || {
    echo "Error: gh is not authenticated. Run 'gh auth login'." >&2
    exit 1
  }

  gh_args=(release create "$tag" "$tarball" --repo "$repo" --title "$title" --notes-file "$notes_tmp")
  if [[ "$prerelease" == "true" ]]; then
    gh_args+=(--prerelease)
  fi

  gh "${gh_args[@]}"
fi

echo "Release $tag created successfully."
