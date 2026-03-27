"""Tests for __main__.py dev server configuration."""


def test_mock_settings_has_projects_dir():
    """S-02: _MockSettings must expose projects_dir, not sessions_dir."""
    from chat_plugin.__main__ import _MockSettings

    settings = _MockSettings()
    assert hasattr(settings, "projects_dir"), (
        "_MockSettings should have 'projects_dir' attribute "
        "(not 'sessions_dir') to match what create_router() reads"
    )
    assert settings.projects_dir is None


def test_mock_settings_no_sessions_dir():
    """S-02: The old sessions_dir attribute should not exist."""
    from chat_plugin.__main__ import _MockSettings

    settings = _MockSettings()
    assert not hasattr(settings, "sessions_dir"), (
        "_MockSettings should NOT have 'sessions_dir' — "
        "it was renamed to 'projects_dir'"
    )
