import pytest

from apartment_planner.model import DoorSpec, Opening, ProjectDoc, new_project
from apartment_planner.state.errors import EditError
from apartment_planner.state.openings import (
    OpeningKind,
    add_opening,
    delete_openings,
    move_opening,
    opening,
    parse_opening_length,
    update_opening,
)
from apartment_planner.state.rooms import add_room, room
from tests.factories import NOW


def flat() -> tuple[ProjectDoc, str, str]:
    """Two rooms; returns the doc and their IDs."""
    doc, left = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    doc, right = add_room(doc, [(400, 0), (460, 0), (460, 300), (400, 300)])
    return doc, left, right


def top_edge(doc: ProjectDoc, room_id: str) -> str:
    return room(doc, room_id).vertices[0].id


DEFAULT_DOOR = DoorSpec(hinge="start", swing="in")
DOOR = "".join(["do", "or"])  # equal to "door" but not the same string, as from a combo box


@pytest.mark.parametrize(
    ("kind", "width", "door"),
    [("door", 80, DEFAULT_DOOR), ("window", 120, None), ("opening", 90, None)],
)
def test_new_openings_get_a_default_width_and_doors_swing_into_the_room(
    kind: OpeningKind, width: float, door: DoorSpec | None
) -> None:
    doc, left, _ = flat()

    doc, added_id = add_opening(doc, kind, left, top_edge(doc, left), 100)

    added = opening(doc, added_id)
    assert (added.width, added.offset, added.door) == (width, 100, door)


def test_new_openings_stay_on_short_walls() -> None:
    doc, _, right = flat()  # its top wall is 60 cm long

    doc, window_id = add_opening(doc, "window", right, top_edge(doc, right), -5)

    window = opening(doc, window_id)
    assert (window.width, window.offset, window.door) == (60, 30, None)


def test_openings_can_move_to_another_room_and_are_clamped_there() -> None:
    doc, left, right = flat()
    doc, door_id = add_opening(doc, "door", left, top_edge(doc, left), 100)

    doc = move_opening(doc, door_id, right, top_edge(doc, right), 55)

    door = opening(doc, door_id)
    assert (door.room_id, door.offset) == (right, 30)


@pytest.mark.parametrize(("offset", "kept"), [(-5, 0.5), (0.6, 0.6)])  # past the start; on it
def test_moving_a_narrow_opening_keeps_it_on_the_wall(offset: float, kept: float) -> None:
    doc, left, _ = flat()
    doc, window_id = add_opening(doc, "window", left, top_edge(doc, left), 100)
    doc = update_opening(doc, window_id, width=1)

    doc = move_opening(doc, window_id, left, top_edge(doc, left), offset)

    assert opening(doc, window_id).offset == kept


@pytest.mark.parametrize(
    ("before", "kind", "door"),
    [
        ("window", "window", None),
        ("door", "window", None),
        ("opening", DOOR, DEFAULT_DOOR),
        ("door", DOOR, DEFAULT_DOOR),
    ],
)
def test_changing_the_kind_adds_or_drops_door_settings(
    before: OpeningKind, kind: str, door: DoorSpec | None
) -> None:
    doc, left, _ = flat()
    doc, opening_id = add_opening(doc, before, left, top_edge(doc, left), 100)

    doc = update_opening(doc, opening_id, kind=kind)

    assert opening(doc, opening_id).door == door


def test_door_settings_can_change_without_changing_the_kind() -> None:
    doc, left, _ = flat()
    doc, door_id = add_opening(doc, "door", left, top_edge(doc, left), 100)

    doc = update_opening(doc, door_id, door=DoorSpec(hinge="end", swing="out"))
    doc = update_opening(doc, door_id, width=90)  # keeps the settings

    door = opening(doc, door_id)
    assert (door.width, door.door) == (90, DoorSpec(hinge="end", swing="out"))


def test_editing_an_opening_leaves_the_others_alone() -> None:
    """Fixed IDs "window-a", "window-c" and "window-b", in that order, so the edited
    one comes after IDs that sort both before and after it."""
    doc, left, _ = flat()
    windows = tuple(
        Opening(
            id=f"window-{name}",
            kind="window",
            room_id=left,
            edge_start_vertex_id=top_edge(doc, left),
            offset=offset,
            width=80,
        )
        for name, offset in [("a", 60), ("c", 200), ("b", 340)]
    )
    doc = doc.evolve(apartment=doc.apartment.evolve(openings=windows))
    window_b = "".join(["window-", "b"])  # equal to the ID, but not the same string

    doc = update_opening(doc, window_b, width=50)

    assert opening(doc, window_b).width == 50
    assert [o.width for o in doc.apartment.openings] == [80, 80, 50]


def test_delete_removes_only_the_given_openings() -> None:
    doc, left, _ = flat()
    doc, first = add_opening(doc, "door", left, top_edge(doc, left), 100)
    doc, second = add_opening(doc, "window", left, top_edge(doc, left), 300)

    doc = delete_openings(doc, [first])

    assert [o.id for o in doc.apartment.openings] == [second]


@pytest.mark.parametrize(("text", "width"), [("60 cm", 60), ("0.6 m", 60), ("0.1", 0.1)])
def test_an_opening_can_be_any_width_up_to_its_wall(text: str, width: float) -> None:
    doc, _, right = flat()  # its top wall is 60 cm long
    doc, window_id = add_opening(doc, "window", right, top_edge(doc, right), 30)

    changes = parse_opening_length(doc, opening(doc, window_id), "width", text, "cm")

    assert changes == {"width": width}


@pytest.mark.parametrize(("text", "unit"), [("60.1", "cm"), ("0", "cm"), ("wide", "m")])
def test_widths_beyond_the_wall_or_unreadable_are_refused(text: str, unit: str) -> None:
    doc, _, right = flat()
    doc, window_id = add_opening(doc, "window", right, top_edge(doc, right), 30)
    expected = "0.6 m" if unit == "m" else "60 cm"

    with pytest.raises(EditError, match=f"at most the wall's {expected}"):
        parse_opening_length(doc, opening(doc, window_id), "width", text, unit)  # type: ignore[arg-type]


def test_offsets_are_read_in_the_display_unit_and_must_be_lengths() -> None:
    doc, left, _ = flat()
    doc, door_id = add_opening(doc, "door", left, top_edge(doc, left), 100)
    door = opening(doc, door_id)

    assert parse_opening_length(doc, door, "offset", " 1.5 m ", "m") == {"offset": 150}
    with pytest.raises(EditError, match="Offset"):
        parse_opening_length(doc, door, "offset", "left", "cm")
