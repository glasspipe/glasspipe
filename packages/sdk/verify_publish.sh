#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}${BOLD}[OK]${RESET} $1"; }
fail() { echo -e "${RED}${BOLD}[FAIL]${RESET} $1"; exit 1; }
step() { echo -e "${BOLD}-->${RESET} $1"; }

cd "$(dirname "$0")"

step "Cleaning old build artifacts"
rm -rf dist build src/*.egg-info *.egg-info
ok "Cleaned"

step "Building package (sdist + wheel)"
python -m build || fail "Build failed"
ok "Build succeeded"

step "Verifying package with twine"
twine check dist/* || fail "Twine check failed"
ok "Twine check passed"

step "Creating fresh virtualenv for install test"
VENV_DIR=$(mktemp -d /tmp/glasspipe-test-XXXXXX)
python3 -m venv "$VENV_DIR" || fail "Could not create venv"
source "$VENV_DIR/bin/activate"
ok "Virtualenv created at $VENV_DIR"

step "Installing wheel into fresh venv"
WHEEL=$(ls dist/glasspipe-*.whl | head -1)
pip install "$WHEEL" -q || fail "Wheel install failed"
ok "Installed $(basename "$WHEEL")"

step "Testing import"
python -c "from glasspipe import trace, span, redact, detect; print('Import OK')" || fail "Import failed"
ok "Import works"

step "Testing CLI"
glasspipe --help || fail "CLI --help failed"
ok "CLI works"

step "Testing version"
python -c "import glasspipe; assert glasspipe.__version__ == '0.1.0', f'Expected 0.1.0, got {glasspipe.__version__}'; print('Version OK')" || fail "Version mismatch"
ok "Version 0.1.0 confirmed"

step "Cleaning up test venv"
deactivate
rm -rf "$VENV_DIR"
ok "Cleaned up"

echo ""
echo -e "${GREEN}${BOLD}All checks passed. Package is ready for publishing.${RESET}"
echo ""
echo "Next steps:"
echo "  1. twine upload --repository testpypi dist/*"
echo "  2. pip install -i https://test.pypi.org/simple/ glasspipe"
echo "  3. Create GitHub release v0.1.0 to trigger auto-publish to PyPI"
