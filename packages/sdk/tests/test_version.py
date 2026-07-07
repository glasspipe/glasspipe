import re

import glasspipe


def test_version_is_semver():
    # Don't pin the exact number — just guarantee it stays well-formed and in
    # sync with pyproject.toml (checked by the packaging pipeline).
    assert re.fullmatch(r"\d+\.\d+\.\d+", glasspipe.__version__)
