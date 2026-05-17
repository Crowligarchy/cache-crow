"""
Pytest configuration and shared fixtures for cache-crow test suite.

All tests use synthetic data — no real Discord installation required.
Integration tests (marked with @pytest.mark.integration) require:
  - DISCORD_TOKEN_B  (Bot/user token with message send permissions)
  - DISCORD_TEST_CHANNEL_ID  (ID of the test channel)

To run integration tests:
  source ~/.crowligarchy/credentials.env
  export DISCORD_TOKEN_B DISCORD_TEST_CHANNEL_ID
  python -m pytest -v -m integration
"""
import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: live Discord API tests — require DISCORD_TOKEN_B and "
        "DISCORD_TEST_CHANNEL_ID environment variables",
    )
