from __future__ import annotations

import pytest

from app.services.knowledge_rag.chunking import ChunkConfig, chunk_document
from app.services.knowledge_rag.domain import BBox, Block, ExtractedDocument, Section
from app.services.knowledge_rag.tokens import MODEL_MAX_WORDPIECES, heuristic_counter
from tests.knowledge_rag_helpers import fake_count

SHA = "ab" * 32


def _doc(*sections: Section) -> ExtractedDocument:
    return ExtractedDocument(sections=list(sections), extractor="test")


def _sentences(n: int, prefix: str = "w") -> str:
    return " ".join(f"Sentence {prefix}{i} talks about margin of safety and value." for i in range(n))


def test_children_respect_token_limit_and_offsets_are_exact() -> None:
    sec = Section(("Cap 1", "Riesgo"), [Block(_sentences(60), page=3), Block(_sentences(40, "z"), page=4)])
    cfg = ChunkConfig(child_max_tokens=60, child_overlap_tokens=10, parent_max_tokens=200)
    parents, children = chunk_document(_doc(sec), title="Libro", source_sha256=SHA, count=fake_count, config=cfg)
    assert len(parents) > 1 and len(children) > len(parents)
    by_id = {p.id: p for p in parents}
    for child in children:
        assert child.token_count <= cfg.child_max_tokens
        parent = by_id[child.parent_id]
        assert parent.text[child.char_start : child.char_end] == child.text
        assert child.embed_text.endswith(child.text)
    assert all(fake_count(p.text) <= cfg.parent_max_tokens + cfg.child_max_tokens for p in parents)


def test_default_config_never_exceeds_minilm_window() -> None:
    sec = Section(("A",), [Block(_sentences(300))])
    cfg = ChunkConfig()
    assert cfg.child_max_tokens < MODEL_MAX_WORDPIECES
    _, children = chunk_document(_doc(sec), title="T", source_sha256=SHA, count=heuristic_counter, config=cfg)
    assert children and max(c.token_count for c in children) <= cfg.child_max_tokens


def test_consecutive_children_overlap() -> None:
    sec = Section(("A",), [Block(_sentences(50))])
    cfg = ChunkConfig(child_max_tokens=60, child_overlap_tokens=12, parent_max_tokens=10_000)
    _, children = chunk_document(_doc(sec), title="T", source_sha256=SHA, count=fake_count, config=cfg)
    assert len(children) > 3
    for prev, nxt in zip(children, children[1:], strict=False):
        assert nxt.char_start < prev.char_end  # solapan
        assert nxt.char_start > prev.char_start  # y avanzan


def test_oversized_sentence_is_hard_split_and_still_fits() -> None:
    monster = "palabra " * 500
    sec = Section(("A",), [Block(monster.strip())])
    cfg = ChunkConfig(child_max_tokens=40, child_overlap_tokens=5, parent_max_tokens=500)
    _, children = chunk_document(_doc(sec), title="T", source_sha256=SHA, count=fake_count, config=cfg)
    assert len(children) >= 500 // 40
    assert max(c.token_count for c in children) <= 40


def test_provenance_pages_and_bboxes_follow_the_blocks() -> None:
    box = BBox(7, 1.0, 2.0, 3.0, 4.0)
    sec = Section(
        ("A",),
        [Block("Primera frase corta aqui.", page=7, bbox=box), Block("Otra frase en otra pagina.", page=8)],
    )
    _, children = chunk_document(_doc(sec), title="T", source_sha256=SHA, count=fake_count)
    assert children[0].page_start == 7 and children[0].page_end == 8
    assert children[0].bboxes == [box]


def test_ids_are_deterministic_and_sections_do_not_mix() -> None:
    a = Section(("A",), [Block(_sentences(5, "a"))])
    b = Section(("B",), [Block(_sentences(5, "b"))])
    p1, c1 = chunk_document(_doc(a, b), title="T", source_sha256=SHA, count=fake_count)
    p2, c2 = chunk_document(_doc(a, b), title="T", source_sha256=SHA, count=fake_count)
    assert [c.id for c in c1] == [c.id for c in c2] and len({c.id for c in c1}) == len(c1)
    assert [p.section_path for p in p1] == [("A",), ("B",)]
    assert all("Sentence a" not in c.text for c in c1 if c.section_path == ("B",))


def test_empty_sections_are_skipped() -> None:
    parents, children = chunk_document(_doc(Section(("A",), [Block("   ")])), title="T", source_sha256=SHA, count=fake_count)
    assert parents == [] and children == []


def test_bad_overlap_config_is_rejected() -> None:
    with pytest.raises(ValueError):
        ChunkConfig(child_max_tokens=60, child_overlap_tokens=40)
