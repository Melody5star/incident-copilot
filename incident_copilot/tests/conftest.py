"""Shared fixtures for all tests."""

import pathlib
import pytest
from dotenv import load_dotenv

# Load .env so every test can read real credentials from env
load_dotenv(pathlib.Path(__file__).parent.parent / ".env")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
