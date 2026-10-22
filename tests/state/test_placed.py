import pytest

from apartment_planner.model import ProjectDoc, RectShape, new_project
from apartment_planner.state.furniture import add_furniture
from apartment_planner.state.placed import (
    add_obstacle,
    delete_placed,
    duplicate_placed,
    move_placed,
    placed_item,
    rotate_placed,
    selectable,
    selected_placed,
    update_placed,
)
from apartment_planner.state.rooms import add_room
from tests.factories import NOW, polygon_shape

COLUMN = RectShape(width=30, depth=30)


def project() -> tuple[ProjectDoc, str, str, str]:
    """A sofa in the layout and two columns in the apartment."""
    doc, sofa = add_furniture(
        new_project("Flat", now=NOW), RectShape(width=200, depth=90), (0, 0), "Sofa"
    )
    doc, first = add_obstacle(doc, COLUMN, (100, 100), "Column")
    doc, second = add_obstacle(doc, COLUMN, (300, 100), "Column")
    return doc, sofa, first, second


def test_obstacles_get_unique_names_and_live_in_the_apartment() -> None:
    doc, _, _, _ = project()
    for _ in range(2):
        doc, _ = add_obstacle(doc, COLUMN, (500, 100), "Column")

    assert [o.name for o in doc.apartment.obstacles] == [
        "Column",
        "Column 2",
        "Column 3",
        "Column 4",
    ]
    assert len(doc.active_layout.furniture) == 1


def test_a_selection_with_obstacles_acts_on_the_obstacles_only() -> None:
    doc, sofa, first, _ = project()

    assert [i.id for i in selected_placed(doc, {sofa, first})] == [first]
    assert [i.id for i in selected_placed(doc, {sofa})] == [sofa]


def test_obstacles_move_rotate_and_update() -> None:
    doc, _, first, second = project()

    doc = move_placed(doc, [first], (10, -5))
    doc = rotate_placed(doc, [first, second], 90)  # about their common centre (205, 97.5)
    doc = update_placed(doc, "".join(second), name="Pillar")  # an equal ID, not the same string

    a, b = placed_item(doc, "".join(first)), placed_item(doc, second)
    assert (a.x, a.y, a.rotation) == pytest.approx((207.5, 2.5, 90))
    assert (b.x, b.y) == pytest.approx((202.5, 192.5))
    assert b.name == "Pillar"


def test_a_single_obstacle_turns_about_its_origin() -> None:
    doc, _, _, _ = project()
    # A triangle whose origin is its corner, not the centre of its bounding box.
    doc, wedge = add_obstacle(doc, polygon_shape((0, 0), (60, 0), (0, 30)), (500, 100), "Wedge")
    doc = update_placed(doc, wedge, rotation=30)

    doc = rotate_placed(doc, [wedge], 90)

    item = placed_item(doc, wedge)
    assert (item.x, item.y, item.rotation) == (500, 100, 120)


def test_furniture_goes_through_the_furniture_edits() -> None:
    doc, sofa, _, _ = project()

    doc = rotate_placed(move_placed(doc, [sofa], (5, 5)), [sofa], 90)

    item = placed_item(doc, sofa)
    assert (item.x, item.y, item.rotation) == (5, 5, 90)


def test_duplicate_and_delete_obstacles() -> None:
    doc, _, first, second = project()
    doc = update_placed(doc, first, rotation=30, color="#808080")

    doc, copies = duplicate_placed(doc, [first], (20, 50))
    (copy_id,) = copies
    copy = placed_item(doc, copy_id)
    assert (copy.name, copy.x, copy.y, copy.rotation, copy.color) == (
        "Column 3",
        120,
        150,
        30,
        "#808080",
    )
    doc = delete_placed(doc, [first, copy_id])
    assert [o.id for o in doc.apartment.obstacles] == [second]


def test_selectable_prefers_furniture_then_apartment_parts_when_editable() -> None:
    doc, sofa, column, _ = project()
    doc, room = add_room(doc, [(0, 0), (400, 0), (400, 300), (0, 300)])
    doc, other = add_room(doc, [(400, 0), (500, 0), (500, 300), (400, 300)])

    assert selectable(doc, [column, sofa, "door"], apartment_editable=True) == {sofa}
    assert selectable(doc, [column, room], apartment_editable=True) == {column}
    assert selectable(doc, [room, other], apartment_editable=True) == {room, other}
    assert selectable(doc, [column, room], apartment_editable=False) == set()
