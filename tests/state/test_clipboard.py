from apartment_planner.model import Opening, ProjectDoc, RectShape, new_project
from apartment_planner.state.clipboard import Clip, copy_selection, paste
from apartment_planner.state.furniture import (
    add_furniture,
    add_layout,
    delete_furniture,
    furniture_item,
    group_furniture,
    set_locked,
)
from apartment_planner.state.placed import add_obstacle, obstacle, update_placed
from apartment_planner.state.rooms import add_room, delete_room, room
from tests.factories import NOW

SEAT = RectShape(width=50, depth=50)


def flat() -> tuple[ProjectDoc, dict[str, str]]:
    """Two rooms side by side, a grouped sofa and chair, a lamp, a column, and a
    window in the living room's top wall."""
    doc, living = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    doc, kitchen = add_room(doc, [(400, 0), (700, 0), (700, 300), (400, 300)])
    doc, sofa = add_furniture(doc, RectShape(width=200, depth=90), (150, 100), "Sofa")
    doc, chair = add_furniture(doc, SEAT, (300, 100), "Chair")
    doc, lamp = add_furniture(doc, SEAT, (350, 250), "Lamp")
    doc, _ = group_furniture(doc, [sofa, chair])
    doc = set_locked(doc, [sofa], True)
    doc, column = add_obstacle(doc, RectShape(width=30, depth=30), (380, 20), "Column")
    doc = update_placed(doc, column, rotation=37, color="#a0b0c0")
    top = room(doc, living).vertices[0].id
    window = Opening(
        id="w", kind="window", room_id=living, edge_start_vertex_id=top, offset=200, width=120
    )
    doc = doc.evolve(apartment=doc.apartment.evolve(openings=(window,)))
    ids = {"living": living, "kitchen": kitchen, "sofa": sofa, "chair": chair}
    return doc, ids | {"lamp": lamp, "column": column}


def test_pasted_furniture_gets_new_ids_names_and_group_and_is_unlocked() -> None:
    doc, ids = flat()
    clip = copy_selection(doc, {ids["sofa"], ids["chair"], ids["lamp"]})
    assert clip is not None and not clip.is_apartment

    doc, pasted = paste(doc, clip, (300, 0))  # into the kitchen

    copies = [
        furniture_item(doc, i) for i in sorted(pasted, key=lambda i: furniture_item(doc, i).x)
    ]
    assert [(c.name, c.x, c.y, c.locked) for c in copies] == [
        ("Sofa 2", 450, 100, False),
        ("Chair 2", 600, 100, False),
        ("Lamp 2", 650, 250, False),
    ]
    assert not pasted & set(ids.values())
    sofa, chair, lamp = copies
    assert sofa.group_id is not None and sofa.group_id == chair.group_id
    assert sofa.group_id != furniture_item(doc, ids["sofa"]).group_id
    assert lamp.group_id is None
    assert {c.room_id for c in copies} == {ids["kitchen"]}
    assert len(doc.active_layout.groups) == 2


def test_a_cut_pastes_back_under_its_own_names_and_in_any_layout() -> None:
    doc, ids = flat()
    clip = copy_selection(doc, {ids["lamp"]})
    assert clip is not None
    doc = delete_furniture(doc, [ids["lamp"]])
    doc, empty = add_layout(doc)
    doc = doc.evolve(active_layout_id=empty)

    doc, pasted = paste(doc, clip, (0, 0))

    (lamp,) = doc.active_layout.furniture
    assert (lamp.id in pasted, lamp.name, lamp.x, lamp.y) == (True, "Lamp", 350, 250)


def test_pasted_obstacles_keep_their_shape_turn_and_colour() -> None:
    doc, ids = flat()
    clip = copy_selection(doc, {ids["column"]})
    assert clip is not None and clip.is_apartment

    doc, (copy_id,) = paste(doc, clip, (-100, 50))

    copy, source = obstacle(doc, copy_id), obstacle(doc, ids["column"])
    assert (copy.name, copy.x, copy.y) == ("Column 2", 280, 70)
    assert (copy.shape, copy.rotation, copy.color) == (source.shape, 37, "#a0b0c0")


def test_pasted_rooms_bring_their_openings_and_reassign_furniture() -> None:
    doc, ids = flat()
    clip = copy_selection(doc, {ids["living"]})
    assert clip is not None
    doc = delete_room(doc, ids["living"])
    assert furniture_item(doc, ids["sofa"]).room_id is None

    doc, (copy_id,) = paste(doc, clip, (0, 0))

    copy = room(doc, copy_id)
    (window,) = doc.apartment.openings
    assert (copy.name, window.room_id, window.offset) == ("Room 1 copy", copy_id, 200)
    assert window.edge_start_vertex_id == copy.vertices[0].id
    assert furniture_item(doc, ids["sofa"]).room_id == copy_id


def test_a_selection_copies_one_kind_and_openings_alone_copy_nothing() -> None:
    doc, ids = flat()

    furniture_first = copy_selection(doc, {ids["lamp"], ids["column"], ids["living"]})
    obstacles_next = copy_selection(doc, {ids["column"], ids["living"]})
    rooms_last = copy_selection(doc, {ids["living"], "w"})

    assert furniture_first == Clip(furniture=(furniture_item(doc, ids["lamp"]),))
    assert obstacles_next is not None and obstacles_next.rooms == ()
    assert rooms_last is not None and [o.id for o in rooms_last.openings] == ["w"]
    assert copy_selection(doc, {"w"}) is None
