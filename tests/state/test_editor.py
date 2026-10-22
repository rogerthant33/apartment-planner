from apartment_planner.model import Layout, ProjectDoc, new_id, new_project
from apartment_planner.state.editor import HISTORY_LIMIT, EditorState
from apartment_planner.state.rooms import add_room
from tests.factories import NOW

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def renamed_layout(doc: ProjectDoc, name: str) -> ProjectDoc:
    return doc.evolve(layouts=(doc.layouts[0].evolve(name=name),))


def test_undo_and_redo_step_through_commits() -> None:
    d0 = new_project("Flat", now=NOW)
    d1 = renamed_layout(d0, "One")
    d2 = renamed_layout(d0, "Two")
    state = EditorState(d0)
    state.commit(d1)
    state.commit(d2)

    state.undo()
    assert state.doc == d1
    state.undo()
    assert state.doc == d0
    assert not state.can_undo
    state.redo()
    state.redo()
    assert state.doc == d2
    assert not state.can_redo
    assert state.revision == 6


def test_a_new_commit_clears_redo() -> None:
    d0 = new_project("Flat", now=NOW)
    state = EditorState(d0)
    state.commit(renamed_layout(d0, "One"))
    state.undo()

    state.commit(renamed_layout(d0, "Two"))

    assert not state.can_redo


def test_committing_an_unchanged_document_adds_no_step() -> None:
    d0 = new_project("Flat", now=NOW)
    state = EditorState(d0)
    changes: list[str] = []
    state.on_document_changed(lambda: changes.append("doc"))

    state.commit(d0.evolve())
    state.update_untracked(d0.evolve())

    assert not state.can_undo
    assert (state.revision, changes) == (0, [])


def test_history_keeps_the_last_200_steps() -> None:
    d0 = new_project("Flat", now=NOW)
    state = EditorState(d0)
    for n in range(HISTORY_LIMIT + 1):
        state.commit(renamed_layout(d0, f"Step {n}"))

    for _ in range(HISTORY_LIMIT):
        state.undo()

    assert HISTORY_LIMIT == 200
    assert state.doc.layouts[0].name == "Step 0"
    assert not state.can_undo


def test_undo_leaves_name_settings_and_active_layout_alone() -> None:
    d0 = new_project("Flat", now=NOW)
    state = EditorState(d0)
    state.commit(add_room(d0, SQUARE)[0])
    second = Layout(id=new_id(), name="Second")
    state.commit(state.doc.evolve(layouts=(*state.doc.layouts, second)))
    settings = state.doc.settings.evolve(apartment_locked=True, grid_size=25)
    state.update_untracked(
        state.doc.evolve(name="Home", settings=settings, active_layout_id=second.id)
    )

    state.undo()  # removes the second layout, so the first becomes active again
    assert (state.doc.name, state.doc.settings) == ("Home", settings)
    assert state.doc.active_layout_id == d0.layouts[0].id
    state.update_untracked(state.doc.evolve(name="House"))
    state.undo()
    assert state.doc.apartment.rooms == ()
    state.redo()

    assert len(state.doc.apartment.rooms) == 1
    assert (state.doc.name, state.doc.settings) == ("House", settings)


def test_selection_loses_what_no_longer_exists_before_listeners_run() -> None:
    d0 = new_project("Flat", now=NOW)
    state = EditorState(d0)
    d1, room_id = add_room(d0, SQUARE)
    state.commit(d1)
    state.select([room_id, d1.apartment.rooms[0].vertices[0].id])
    state.select([room_id])  # a smaller selection replaces a larger one
    seen: list[frozenset[str]] = []
    selection_changes: list[frozenset[str]] = []
    state.on_document_changed(lambda: seen.append(state.selection))
    state.on_selection_changed(lambda: selection_changes.append(state.selection))
    state.select([room_id])  # the same selection again is no change

    state.commit(renamed_layout(d1, "Kept"))  # the room stays, and so does its selection
    assert selection_changes == []
    state.undo()
    state.undo()

    assert seen == [frozenset({room_id}), frozenset({room_id}), frozenset()]
    assert selection_changes == [frozenset()]
