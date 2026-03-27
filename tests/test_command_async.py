"""Structural test: create_command_routes must use asyncio.to_thread for handle_command.

S-04: Offload blocking /fork command handler to a thread to prevent event loop blocking.
"""

from __future__ import annotations

import inspect


def test_dispatch_command_uses_to_thread():
    """create_command_routes() source must use asyncio.to_thread with handle_command.

    This is a structural test per spec S-04. The production code must offload
    processor.handle_command() to a thread via asyncio.to_thread() to prevent
    event loop blocking when the /fork command handler is dispatched.
    """
    from chat_plugin.routes import create_command_routes

    source = inspect.getsource(create_command_routes)

    assert "to_thread" in source, (
        "create_command_routes() must use asyncio.to_thread() to offload "
        "processor.handle_command() to a thread (S-04: prevents event loop blocking)"
    )
    assert "handle_command" in source, (
        "create_command_routes() source must contain 'handle_command' call "
        "(confirms the dispatch path is present)"
    )
