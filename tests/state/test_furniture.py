import pytest

from apartment_planner.model import (
    Apartment,
    Group,
    Layout,
    PolygonShape,
    ProjectDoc,
    RectShape,
    new_project,
)
from apartment_planner.state.errors import EditError
from apartment_planner.state.furniture import (
    add_furniture,
    add_layout,
    add_polygon_furniture,
    delete_furniture,
    delete_layout,
    duplicate_furniture,
    duplicate_layout,
    furniture_item,
    group_furniture,
    move_furniture,
    move_shape_point,
    rename_layout,
    rotate_furniture,
    set_locked,
    set_shape_edge_length,
    ungroup_furniture,
    update_furniture,
    with_groups,
)
from tests.factories import NOW, rect_room

SOFA = RectShape(width=200, depth=90)


def flat() -> ProjectDoc:
    """A project with one 400 by 300 cm room at the origin."""
    room = rect_room(0, 0, 400, 300, "Living room").evolve(id="living")
    return new_project("Flat", now=NOW).evolve(apartment=Apartment(rooms=(room,)))


def with_items(*positions: tuple[float, float]) -> tuple[ProjectDoc, list[str]]:
    doc, ids = flat(), []
    for position in positions:
        doc, item_id = add_furniture(doc, SOFA, position, "Sofa")
        ids.append(item_id)
    return doc, ids


def position(doc: ProjectDoc, item_id: str) -> tuple[float, float]:
    item = furniture_item(doc, item_id)
    return (item.x, item.y)


def test_new_items_get_unique_names_and_the_room_they_stand_in() -> None:
    doc, (inside, outside) = with_items((100, 100), (900, 100))
    doc, third = add_furniture(doc, SOFA, (50, 50), "Sofa")

    names = [furniture_item(doc, i).name for i in (inside, outside, third)]
    assert names == ["Sofa", "Sofa 2", "Sofa 3"]
    assert furniture_item(doc, inside).room_id == "living"
    assert furniture_item(doc, outside).room_id is None


def test_moving_updates_the_room() -> None:
    doc, (sofa,) = with_items((100, 100))

    doc = move_furniture(doc, [sofa], (800, 0))

    assert position(doc, sofa) == (900, 100)
    assert furniture_item(doc, sofa).room_id is None


def test_locked_items_refuse_to_move_but_can_be_renamed() -> None:
    doc, (sofa, chair) = with_items((100, 100), (300, 100))
    doc = set_locked(doc, [sofa], True)

    with pytest.raises(EditError, match='"Sofa" is locked'):
        move_furniture(doc, [sofa, chair], (10, 0))
    with pytest.raises(EditError, match="locked"):
        update_furniture(doc, sofa, rotation=90)
    assert furniture_item(update_furniture(doc, sofa, name="Couch"), sofa).name == "Couch"


def test_one_item_rotates_about_its_origin() -> None:
    doc, (sofa,) = with_items((100, 100))

    doc = rotate_furniture(doc, [sofa], -90)

    assert position(doc, sofa) == (100, 100)
    assert furniture_item(doc, sofa).rotation == 270


def test_several_items_rotate_about_their_common_centre() -> None:
    # Footprints span x 0..400, y 55..145: the centre is (200, 100).
    doc, (left, right) = with_items((100, 100), (300, 100))

    doc = rotate_furniture(doc, [left, right], 90)

    assert position(doc, left) == pytest.approx((200, 0))
    assert position(doc, right) == pytest.approx((200, 200))
    assert furniture_item(doc, left).rotation == 90


def test_groups_select_together() -> None:
    doc, (a, b, c) = with_items((50, 50), (150, 50), (250, 50))
    doc, _ = group_furniture(doc, [a, b])

    assert with_groups(doc, [a]) == {a, b}
    assert with_groups(doc, [c]) == {c}


def test_grouping_needs_two_items_and_regrouping_dissolves_lone_groups() -> None:
    doc, (a, b, c) = with_items((50, 50), (150, 50), (250, 50))
    with pytest.raises(EditError, match="at least two"):
        group_furniture(doc, [a])
    doc, first = group_furniture(doc, [a, b])

    doc, second = group_furniture(doc, [b, c])

    assert [g.id for g in doc.active_layout.groups] == [second]
    assert furniture_item(doc, a).group_id is None
    assert {furniture_item(doc, i).group_id for i in (b, c)} == {second}
    assert first != second


def test_ungrouping_removes_the_group() -> None:
    doc, (a, b) = with_items((50, 50), (150, 50))
    doc, _ = group_furniture(doc, [a, b])

    doc = ungroup_furniture(doc, [a, b])

    assert doc.active_layout.groups == ()
    assert furniture_item(doc, a).group_id is None


def test_duplicates_are_unlocked_offset_copies_in_a_new_group() -> None:
    doc, (a, b) = with_items((50, 50), (150, 50))
    doc, group = group_furniture(doc, [a, b])
    doc = set_locked(doc, [a], True)

    doc, copies = duplicate_furniture(doc, [a, b], (0, 100))

    items = [furniture_item(doc, i) for i in sorted(copies, key=lambda i: position(doc, i))]
    assert [(i.x, i.y) for i in items] == [(50, 150), (150, 150)]
    assert [i.name for i in items] == ["Sofa 3", "Sofa 4"]
    assert not any(i.locked for i in items)
    (new_group,) = {i.group_id for i in items}
    assert new_group not in (None, group)
    assert len(doc.active_layout.groups) == 2


def test_deleting_a_group_member_dissolves_a_group_of_two() -> None:
    doc, (a, b) = with_items((50, 50), (150, 50))
    doc, _ = group_furniture(doc, [a, b])

    doc = delete_furniture(doc, [a])

    assert [f.id for f in doc.active_layout.furniture] == [b]
    assert doc.active_layout.groups == ()
    assert furniture_item(doc, b).group_id is None


def test_drawn_polygon_is_centred_on_its_bounding_box() -> None:
    doc, item_id = add_polygon_furniture(flat(), [(100, 100), (200, 100), (200, 140)])

    item = furniture_item(doc, item_id)
    assert (item.x, item.y) == (150, 120)
    assert isinstance(item.shape, PolygonShape)
    assert [(p.x, p.y) for p in item.shape.points] == [(-50, -20), (50, -20), (50, 20)]


def test_invalid_drawn_polygon_is_refused() -> None:
    with pytest.raises(EditError, match="crosses itself"):
        add_polygon_furniture(flat(), [(0, 0), (100, 100), (100, 0), (0, 100)])


def test_polygon_corners_move_in_the_items_own_frame() -> None:
    doc, item_id = add_polygon_furniture(flat(), [(100, 100), (200, 100), (200, 140)])
    doc = rotate_furniture(doc, [item_id], 90)  # local +x now points down

    doc = move_shape_point(doc, item_id, 2, (130, 180))
    doc = set_shape_edge_length(doc, item_id, 0, 50)

    shape = furniture_item(doc, item_id).shape
    assert isinstance(shape, PolygonShape)
    assert [c for p in shape.points for c in (p.x, p.y)] == pytest.approx(
        [-50, -20, 0, -20, 60, 20]
    )


def test_layouts_can_be_added_renamed_duplicated_and_deleted() -> None:
    doc, (sofa,) = with_items((100, 100))
    first = doc.active_layout_id

    doc, copy_id = duplicate_layout(doc, first)
    doc, empty = add_layout(doc)
    doc = rename_layout(doc, empty, "  Bare  ")

    copy = doc.layout(copy_id)
    assert [layout.name for layout in doc.layouts] == ["Layout 1", "Layout 1 copy", "Bare"]
    assert copy.furniture[0].id != sofa
    assert copy.furniture[0].name == "Sofa"
    doc = doc.evolve(active_layout_id=copy_id)
    doc = delete_layout(doc, copy_id)
    assert doc.active_layout_id == empty
    with pytest.raises(EditError, match="Enter a name"):
        rename_layout(doc, empty, " ")


def test_the_last_layout_cannot_be_deleted() -> None:
    doc = flat()

    with pytest.raises(EditError, match="at least one layout"):
        delete_layout(doc, doc.active_layout_id)


def test_duplicated_layout_keeps_groups_with_new_ids() -> None:
    doc, (a, b) = with_items((50, 50), (150, 50))
    doc, group = group_furniture(doc, [a, b])

    doc, copy_id = duplicate_layout(doc, doc.active_layout_id)

    copy = doc.layout(copy_id)
    (copied_group,) = copy.groups
    assert copied_group.id != group
    assert {f.group_id for f in copy.furniture} == {copied_group.id}


def test_furniture_edits_act_on_the_active_layout_only() -> None:
    doc, (sofa,) = with_items((100, 100))
    other = Layout(id="other", name="Other", groups=(Group(id="g", name="G"),))
    doc = doc.evolve(layouts=(*doc.layouts, other))

    doc = move_furniture(doc, [sofa], (10, 10))

    assert doc.layout("other") == other
