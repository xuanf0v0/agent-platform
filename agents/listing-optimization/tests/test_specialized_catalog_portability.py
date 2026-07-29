from __future__ import annotations

import re
from pathlib import Path
from typing import Final

CATALOG_SUPPORT_SOURCE: Final = Path(__file__).with_name("specialized_catalog_support.py")
USER_SPECIFIC_WINDOWS_PATH: Final = re.compile(r"[A-Za-z]:\\Users\\[^\\]+\\")


def test_catalog_support_has_no_user_specific_absolute_resource_path() -> None:
    # Given: the test support module that supplies specialized-rule resources.
    source = CATALOG_SUPPORT_SOURCE.read_text(encoding="utf-8")

    # When: executable string literals are inspected for a user-profile path.
    match = USER_SPECIFIC_WINDOWS_PATH.search(source)

    # Then: collection must not depend on one developer's filesystem.
    assert match is None
