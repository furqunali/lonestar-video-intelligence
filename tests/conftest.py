"""Shared pytest fixtures."""
from __future__ import annotations

import pytest

from avip.common.config import load_config
from avip.db.models import init_db, make_engine


@pytest.fixture
def config():
    """The real project config (config/*.yaml), loaded + validated."""
    return load_config()


@pytest.fixture
def engine(tmp_path):
    """A fresh SQLite database in a temp dir, schema created."""
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(eng)
    return eng
