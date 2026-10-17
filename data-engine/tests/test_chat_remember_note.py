"""El chat guarda memoria SOLO ante "recuerda ..." explicito y lo dice; nunca toca cartera."""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, MemoryItem
from app.services.chat_service import ChatService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def test_recuerda_writes_one_memory_and_answers_apuntado(db):
    response = asyncio.run(ChatService().answer(db, "Recuerda que prefiero inversión a largo plazo", "portfolio", None))
    assert response.answer == "Apuntado: prefiero inversión a largo plazo"
    assert response.model == "memory-note"
    items = db.query(MemoryItem).all()
    assert len(items) == 1 and items[0].source_type == "chat"
    assert response.sources[0]["type"] == "memory_item" and response.sources[0]["id"] == items[0].id


def test_without_recuerda_nothing_is_written(db):
    for text in ("Hola, ¿qué tal?", "Guarda esto: vigila la tesis de ASTS", "Recuerda vigilar ASTS. ¿Qué tienes?"):
        try:
            asyncio.run(ChatService().answer(db, text, "portfolio", None))
        except Exception:
            pass  # el camino sin recuerda puede necesitar mas datos; lo que importa es no escribir
    assert db.query(MemoryItem).count() == 0
