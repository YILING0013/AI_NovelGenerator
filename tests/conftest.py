from __future__ import annotations

import sys
import uuid
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def unique_title() -> Callable[[str], str]:
    def _build(prefix: str) -> str:
        return f"__pytest_{prefix}_{uuid.uuid4().hex[:8]}__"

    return _build


@pytest.fixture
def create_novel(client: TestClient, unique_title: Callable[[str], str]):
    created_novel_ids: list[str] = []

    def _create(prefix: str = "novel") -> str:
        response = client.post(
            "/api/novels/create",
            json={
                "title": unique_title(prefix),
                "genre": "test",
            },
        )
        assert response.status_code == 200, response.text
        novel_id = response.json()["id"]
        created_novel_ids.append(novel_id)
        return novel_id

    yield _create

    for novel_id in reversed(created_novel_ids):
        client.delete(f"/api/novels/{novel_id}")
        client.delete(f"/api/novels/{novel_id}/hard")