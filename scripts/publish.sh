#!/usr/bin/env bash
# Publish dist/ to TestPyPI or PyPI (roadmap S2, D-012). The owner runs this; the
# token is read without echo and never written anywhere.
#
#   scripts/publish.sh testpypi
#   scripts/publish.sh pypi
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  testpypi) URL="https://test.pypi.org/legacy/"; SITE="test.pypi.org" ;;
  pypi) URL="https://upload.pypi.org/legacy/"; SITE="pypi.org" ;;
  *) echo "usage: $0 testpypi|pypi"; exit 2 ;;
esac

VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
rm -rf dist
uv build -q
ls dist/cigar_break-"$VERSION"-py3-none-any.whl dist/cigar_break-"$VERSION".tar.gz >/dev/null
echo "About to upload cigar-break $VERSION to $SITE:"
ls -1 dist/
read -rsp "Paste a $SITE API token (input hidden): " UV_PUBLISH_TOKEN
echo
UV_PUBLISH_TOKEN="$UV_PUBLISH_TOKEN" uv publish --publish-url "$URL" dist/*
echo "Done: https://$SITE/project/cigar-break/$VERSION/"
