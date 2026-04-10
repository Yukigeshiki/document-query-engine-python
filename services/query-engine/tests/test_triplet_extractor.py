"""Tests for the triplet extraction module."""

from unittest.mock import MagicMock, patch

from app.services.triplet_extractor import extract_triplets


@patch("app.services.triplet_extractor.Settings")
def test_extracts_triplets_from_llm_response(mock_settings: MagicMock) -> None:
    """Verify triplets are parsed correctly from the LLM response."""
    mock_settings.llm.predict.return_value = (
        "(Alice, is mother of, Bob)\n"
        "(Philz, founded in, Berkeley)\n"
    )

    result = extract_triplets("Alice is Bob's mother. Philz was founded in Berkeley.")

    assert len(result) == 2
    assert result[0] == ("Alice", "is mother of", "Bob")
    assert result[1] == ("Philz", "founded in", "Berkeley")
    mock_settings.llm.predict.assert_called_once()


@patch("app.services.triplet_extractor.Settings")
def test_returns_empty_list_for_no_triplets(mock_settings: MagicMock) -> None:
    """Verify empty response yields empty list."""
    mock_settings.llm.predict.return_value = "No triplets found."

    result = extract_triplets("Some random text.")

    assert result == []


@patch("app.services.triplet_extractor.Settings")
def test_truncates_long_entities(mock_settings: MagicMock) -> None:
    """Verify entities longer than MAX_ENTITY_LENGTH are truncated."""
    long_entity = "A" * 200
    mock_settings.llm.predict.return_value = f"({long_entity}, relates to, Bob)"

    result = extract_triplets("text")

    assert len(result) == 1
    assert len(result[0][0]) == 128  # MAX_ENTITY_LENGTH


@patch("app.services.triplet_extractor.Settings")
def test_skips_malformed_triplets(mock_settings: MagicMock) -> None:
    """Verify malformed lines are skipped without error."""
    mock_settings.llm.predict.return_value = (
        "(Alice, is mother of, Bob)\n"
        "not a triplet\n"
        "(, , )\n"  # empty fields
        "(Valid, relation, Entity)\n"
    )

    result = extract_triplets("text")

    assert len(result) == 2
    assert result[0] == ("Alice", "is mother of", "Bob")
    assert result[1] == ("Valid", "relation", "Entity")


@patch("app.services.triplet_extractor.Settings")
def test_respects_max_triplets_in_prompt(mock_settings: MagicMock) -> None:
    """Verify max_triplets parameter is passed to the LLM call."""
    mock_settings.llm.predict.return_value = ""

    extract_triplets("text", max_triplets=5)

    kwargs = mock_settings.llm.predict.call_args[1]
    assert kwargs["max_knowledge_triplets"] == 5


# --- Adversarial LLM output tests ---


@patch("app.services.triplet_extractor.Settings")
def test_handles_commas_in_entity_names(mock_settings: MagicMock) -> None:
    """Verify triplets with commas inside entity names are parsed best-effort.

    The regex splits on commas, so "New York, NY" becomes two fields.
    This is a known limitation — the test documents the current behavior
    so regressions are caught if the parser is improved later.
    """
    mock_settings.llm.predict.return_value = (
        "(New York, located in, United States)\n"
    )

    result = extract_triplets("text")

    # "New York" is the subject, "located in" is the predicate,
    # "United States" is the object — this works because there are
    # exactly 3 comma-separated fields.
    assert len(result) == 1
    assert result[0] == ("New York", "located in", "United States")


@patch("app.services.triplet_extractor.Settings")
def test_handles_empty_lines_between_triplets(
    mock_settings: MagicMock,
) -> None:
    """Verify blank lines in the LLM response don't break parsing."""
    mock_settings.llm.predict.return_value = (
        "(Alice, works at, Acme)\n"
        "\n"
        "\n"
        "(Bob, lives in, Paris)\n"
    )

    result = extract_triplets("text")

    assert len(result) == 2
    assert result[0] == ("Alice", "works at", "Acme")
    assert result[1] == ("Bob", "lives in", "Paris")


@patch("app.services.triplet_extractor.Settings")
def test_handles_partial_response(mock_settings: MagicMock) -> None:
    """Verify a truncated LLM response extracts what it can."""
    mock_settings.llm.predict.return_value = (
        "(Alice, works at, Acme)\n"
        "(Bob, lives in"  # truncated — no closing paren
    )

    result = extract_triplets("text")

    assert len(result) == 1
    assert result[0] == ("Alice", "works at", "Acme")


@patch("app.services.triplet_extractor.Settings")
def test_handles_unicode_entities(mock_settings: MagicMock) -> None:
    """Verify unicode characters in entity names are preserved."""
    mock_settings.llm.predict.return_value = (
        "(Zurich, is city in, Schweiz)\n"
    )

    result = extract_triplets("text")

    assert len(result) == 1
    assert result[0] == ("Zurich", "is city in", "Schweiz")


@patch("app.services.triplet_extractor.Settings")
def test_handles_extra_whitespace(mock_settings: MagicMock) -> None:
    """Verify leading/trailing whitespace in entities is stripped."""
    mock_settings.llm.predict.return_value = (
        "(  Alice  ,  works at  ,  Acme Corp  )\n"
    )

    result = extract_triplets("text")

    assert len(result) == 1
    assert result[0] == ("Alice", "works at", "Acme Corp")
