"""Prompt versioning (EP-13-T04, `could`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from example_agent.prompts.store import PromptVersionStore, UnknownPromptError

REPO_ROOT = Path(__file__).parents[2]
V1_PROMPT = REPO_ROOT / "agents" / "example_agent" / "prompts" / "v1.txt"


def test_publish_creates_version_one_for_a_new_prompt() -> None:
    store = PromptVersionStore()

    version = store.publish("system", "hello")

    assert version.version == 1
    assert version.content == "hello"


def test_a_prompt_change_creates_a_new_version_without_overwriting_the_previous_one() -> None:
    store = PromptVersionStore()
    store.publish("system", "v1 content")

    second = store.publish("system", "v2 content")

    history = store.history("system")
    assert [v.content for v in history] == ["v1 content", "v2 content"]
    assert second.version == 2


def test_latest_returns_the_most_recently_published_version() -> None:
    store = PromptVersionStore()
    store.publish("system", "v1 content")
    store.publish("system", "v2 content")

    assert store.latest("system").content == "v2 content"


def test_publishing_identical_content_still_creates_a_new_trackable_version() -> None:
    store = PromptVersionStore()
    store.publish("system", "same content")

    second = store.publish("system", "same content")

    assert second.version == 2
    assert len(store.history("system")) == 2


def test_latest_raises_for_an_unpublished_prompt_name() -> None:
    store = PromptVersionStore()

    with pytest.raises(UnknownPromptError):
        store.latest("does-not-exist")


def test_the_seed_v1_prompt_file_can_be_published() -> None:
    store = PromptVersionStore()
    content = V1_PROMPT.read_text(encoding="utf-8").strip()

    version = store.publish("example-agent-system", content)

    assert version.content == content
    assert "tools you are given" in version.content
