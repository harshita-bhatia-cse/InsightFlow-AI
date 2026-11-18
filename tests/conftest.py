import pytest

from app.auth import clear_auth_rate_limits
from app.config.settings import settings


@pytest.fixture(autouse=True)
def test_auth_rate_limits():
    original_limit = settings.auth_rate_limit_requests
    object.__setattr__(settings, "auth_rate_limit_requests", 1000)
    clear_auth_rate_limits()
    yield
    clear_auth_rate_limits()
    object.__setattr__(settings, "auth_rate_limit_requests", original_limit)
