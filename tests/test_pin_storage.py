from chat_plugin.pin_storage import PinStorage


def test_pin_and_list(tmp_path):
    store = PinStorage(tmp_path / "pins.json")
    store.add("session-1")
    store.add("session-2")
    assert store.list_pins() == {"session-1", "session-2"}


def test_pin_idempotent(tmp_path):
    store = PinStorage(tmp_path / "pins.json")
    store.add("session-1")
    store.add("session-1")  # no error
    assert len(store.list_pins()) == 1


def test_unpin(tmp_path):
    store = PinStorage(tmp_path / "pins.json")
    store.add("session-1")
    store.remove("session-1")
    assert store.list_pins() == set()


def test_unpin_nonexistent_is_noop(tmp_path):
    store = PinStorage(tmp_path / "pins.json")
    store.remove("nonexistent")  # no error


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "pins.json"
    PinStorage(path).add("session-1")
    store2 = PinStorage(path)
    assert "session-1" in store2.list_pins()


def test_pin_records_timestamp(tmp_path):
    store = PinStorage(tmp_path / "pins.json")
    store.add("session-1")
    ts = store.get_pins_with_timestamps()
    assert "session-1" in ts
    assert ts["session-1"] != ""  # ISO timestamp present


def test_unpin_removes_timestamp(tmp_path):
    store = PinStorage(tmp_path / "pins.json")
    store.add("session-1")
    store.remove("session-1")
    ts = store.get_pins_with_timestamps()
    assert "session-1" not in ts


def test_backward_compat_old_format(tmp_path):
    """Old pin files without pinned_at should still load."""
    path = tmp_path / "pins.json"
    path.write_text('{"pinned": ["session-old"]}', encoding="utf-8")
    store = PinStorage(path)
    assert "session-old" in store.list_pins()
    ts = store.get_pins_with_timestamps()
    assert ts["session-old"] == ""  # no timestamp for old entries
