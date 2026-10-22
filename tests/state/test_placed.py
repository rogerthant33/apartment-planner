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
    selected_placed,
    update_placed,
)
from tests.factories import NOW

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

    assert [o.name for o in doc.apartment.obstacles] == ["Column", "Column 2"]
    assert len(doc.active_layout.furniture) == 1


def test_a_selection_with_obstacles_acts_on_the_obstacles_only() -> None:
    doc, sofa, first, _ = project()

    assert [i.id for i in selected_placed(doc, {sofa, first})] == [first]
    assert [i.id for i in selected_placed(doc, {sofa})] == [sofa]


def test_obstacles_move_rotate_and_update() -> None:
    doc, _, first, second = project()

    doc = move_placed(doc, [first], (10, -5))
    doc = rotate_placed(doc, [first, second], 90)  # about their common centre (205, 97.5)
    doc = update_placed(doc, second, name="Pillar")

    a, b = placed_item(doc, first), placed_item(doc, second)
    assert (a.x, a.y, a.rotation) == pytest.approx((207.5, 2.5, 90))
    assert (b.x, b.y) == pytest.approx((202.5, 192.5))
    assert b.name == "Pillar"


def test_furniture_goes_through_the_furniture_edits() -> None:
    doc, sofa, _, _ = project()

    doc = rotate_placed(move_placed(doc, [sofa], (5, 5)), [sofa], 90)

    item = placed_item(doc, sofa)
    assert (item.x, item.y, item.rotation) == (5, 5, 90)


def test_duplicate_and_delete_obstacles() -> None:
    doc, _, first, second = project()
    doc = update_placed(doc, first, rotation=30, color="#808080")

    doc, copies = duplicate_placed(doc, [first], (0, 50))
    (copy_id,) = copies
    copy = placed_item(doc, copy_id)
    assert (copy.name, copy.x, copy.y, copy.rotation, copy.color) == (
        "Column 3",
        100,
        150,
        30,
        "#808080",
    )
    doc = delete_placed(doc, [first, copy_id])
    assert [o.id for o in doc.apartment.obstacles] == [second]
