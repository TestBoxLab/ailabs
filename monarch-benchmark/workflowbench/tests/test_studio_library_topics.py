"""Library topics come from one fixed list. A source is filed by its own words, lands
in Other when nothing fits, can be moved by Genesis or a person, and old free-text
topics are migrated when the library opens."""
import json

import pytest

from wb_results.evidence import write_json
from wb_studio.library import KEYWORDS, TOPICS, Library, classify


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / "library")


def test_every_topic_but_other_has_keywords_and_other_is_last():
    assert TOPICS[-1] == "Other" and set(KEYWORDS) == set(TOPICS[:-1])


@pytest.mark.parametrize("texts, topic", [
    (("Sleep-time compute: agents consolidate memory while idle",), "Agentic memory"),
    (("Codebase-Memory: tree-sitter knowledge graphs for code exploration",), "Code understanding"),
    (("A leaderboard of agent benchmarks with pass rate and a grader",), "Evaluation and benchmarks"),
    (("Quarterly newsletter about cats",), "Other"),
])
def test_classify_files_by_keywords_and_falls_back_to_other(texts, topic):
    assert classify(*texts) == topic


def test_add_keeps_a_listed_topic_and_classifies_a_free_one(library):
    kept = library.add({"title": "Any", "url": "https://a.example/1", "topic": "UI and design"})
    assert kept["topic"] == "UI and design" and kept["topic_source"] == "human"
    filed = library.add({"title": "Prompt caching cuts token cost by half", "url": "https://a.example/2", "topic": "notes from Tuesday"})
    assert filed["topic"] == "Cost and efficiency" and filed["topic_source"] == "keywords"
    assert library.add({"title": "Untitled", "url": "https://a.example/3"})["topic"] == "Other"


def test_reclassify_accepts_only_listed_topics_and_records_who(library):
    record = library.add({"title": "Untitled", "url": "https://a.example/1"})
    moved = library.reclassify(record["id"], {"topic": "Agent architectures", "by": "genesis"})
    assert moved["topic"] == "Agent architectures" and moved["topic_source"] == "genesis"
    with pytest.raises(ValueError):
        library.reclassify(record["id"], {"topic": "Whatever"})


def test_old_free_text_topics_are_migrated_when_the_library_opens(tmp_path):
    folder = tmp_path / "library"
    folder.mkdir()
    write_json(folder / "old.json", {"id": "old", "title": "Wilson intervals for pass rate", "authors": [], "source_type": "paper", "url": "https://a.example/old",
                                     "published_at": None, "discovered_at": "2026-09-01", "topic": "Design comparable architecture experiments",
                                     "status": "saved", "abstract": "", "full_text_available": False, "original": None, "analysis": None,
                                     "used_in": [], "contradicts": [], "created_at": "2026-09-01T00:00:00+00:00"})
    library = Library(folder)
    record = json.loads((folder / "old.json").read_text(encoding="utf-8"))
    assert record["topic"] == "Evaluation and benchmarks" and record["topic_source"] == "keywords"
    assert [r["topic"] for r in library.listing()] == ["Evaluation and benchmarks"]


def test_ledger_import_files_each_source_in_a_listed_topic(library, tmp_path):
    ledger = tmp_path / "search-log.jsonl"
    ledger.write_text(json.dumps({"id": "hermes", "date": "2026-09-09", "url": "https://hermes.example/memory", "title": "Hermes Agent memory",
                                  "finding": "Bounded memory files and FTS5 recall", "motivation": "Give Genesis a memory", "access_status": "full_text_read"}) + "\n",
                      encoding="utf-8")
    library.import_ledger(ledger)
    assert library.read("hermes")["topic"] == "Agentic memory"
