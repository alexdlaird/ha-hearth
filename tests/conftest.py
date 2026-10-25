__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    return
