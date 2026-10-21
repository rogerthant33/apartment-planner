from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from apartment_planner.model import (
    Apartment,
    BackgroundImage,
    DoorSpec,
    EllipseShape,
    FurnitureItem,
    Group,
    Layout,
    Opening,
    Point,
    ProjectDoc,
    ProjectSettings,
    RectShape,
    Room,
    new_id,
    new_project,
)
from tests.factories import item, polygon_shape, rect_item, rect_room

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def full_project() -> ProjectDoc:
    """A project touching every model type."""
    room = rect_room(0, 0, 400, 300, "Living room")
    door = Opening(
        id=new_id(),
        kind="door",
        room_id=room.id,
        edge_start_vertex_id=room.vertices[0].id,
        offset=100,
        width=80,
        door=DoorSpec(hinge="start", swing="in"),
    )
    window = Opening(
        id=new_id(),
        kind="window",
        room_id=room.id,
        edge_start_vertex_id=room.vertices[2].id,
        offset=200,
        width=120,
    )
    group = Group(id=new_id(), name="Dining set")
    table = item(EllipseShape(rx=60, ry=60), 200, 150).evolve(group_id=group.id, room_id=room.id)
    layout_a = Layout(
        id=new_id(),
        name="Sofa by window",
        furniture=(rect_item(200, 90, 100, 50, rotation=90), table),
        groups=(group,),
    )
    layout_b = Layout(
        id=new_id(),
        name="L-sofa",
        furniture=(item(polygon_shape((0, 0), (100, 0), (100, 50), (0, 50))),),
    )
    base = new_project("Flat", now=NOW)
    return base.evolve(
        apartment=Apartment(rooms=(room,), openings=(door, window)),
        layouts=(layout_a, layout_b),
        active_layout_id=layout_b.id,
    )


def background(**changes: Any) -> BackgroundImage:
    return BackgroundImage(
        asset_id="a", mime_type="image/png", origin=Point(x=0, y=0), cm_per_pixel=1, **changes
    )


def revalidate(doc: ProjectDoc, **changes: Any) -> ProjectDoc:
    data = doc.model_dump(mode="json")
    data.update(changes)
    return ProjectDoc.model_validate(data)


def test_new_project_is_valid_with_one_active_layout() -> None:
    doc = new_project("Flat", now=NOW)

    assert doc.name == "Flat"
    assert doc.created_at == doc.updated_at == NOW
    assert len(doc.layouts) == 1
    assert doc.active_layout is doc.layouts[0]
    assert ProjectDoc.model_validate(doc.model_dump()) == doc


def test_layout_lookup_matches_ids_by_value() -> None:
    doc = full_project()

    for layout in doc.layouts:
        assert doc.layout("".join(layout.id)) is layout  # an equal string, not the same one
    with pytest.raises(KeyError):
        doc.layout("missing")


def test_json_round_trip_is_lossless() -> None:
    doc = full_project()

    restored = ProjectDoc.model_validate_json(doc.model_dump_json())

    assert restored == doc


def test_rotation_is_normalised_to_0_360() -> None:
    assert rect_item(10, 10, rotation=-90).rotation == 270
    assert rect_item(10, 10, rotation=450).rotation == 90
    assert rect_item(10, 10, rotation=360).rotation == 0
    assert rect_item(10, 10, rotation=-1e-20).rotation == 0


def test_evolve_revalidates_fields_and_references() -> None:
    assert rect_item(10, 10).evolve(rotation=-90).rotation == 270
    with pytest.raises(ValidationError, match="active_layout_id"):
        full_project().evolve(active_layout_id="nope")


def test_rejects_counter_clockwise_room() -> None:
    room = rect_room(0, 0, 400, 300)

    with pytest.raises(ValidationError, match="counter-clockwise"):
        room.evolve(vertices=tuple(reversed(room.vertices)))


def test_models_are_frozen() -> None:
    doc = new_project("Flat")

    with pytest.raises(ValidationError):
        doc.name = "Other"  # type: ignore[misc]


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_rejects_non_finite_numbers(bad: float) -> None:
    with pytest.raises(ValidationError):
        RectShape(width=bad, depth=10)


def test_rejects_unknown_fields() -> None:
    data = full_project().model_dump(mode="json")
    data["layouts"][0]["furniture"][0]["colour"] = "#ff0000"

    with pytest.raises(ValidationError, match="colour"):
        ProjectDoc.model_validate(data)


def test_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValidationError):
        RectShape(width=0, depth=10)


def test_rooms_and_polygons_need_three_points() -> None:
    triangle = rect_room(0, 0, 100, 100).vertices[:3]
    Room(id="r", name="Nook", vertices=triangle)
    polygon_shape((0, 0), (10, 0), (0, 10))

    with pytest.raises(ValidationError):
        Room(id="r", name="Nook", vertices=triangle[:2])
    with pytest.raises(ValidationError):
        polygon_shape((0, 0), (10, 0))


def test_names_and_ids_must_not_be_empty() -> None:
    Group(id="g", name="A")

    with pytest.raises(ValidationError):
        Group(id="g", name="")
    with pytest.raises(ValidationError):
        Group(id="", name="A")


def test_rejects_negative_offsets() -> None:
    with pytest.raises(ValidationError, match="offset"):
        Opening(id="o", kind="window", room_id="r", edge_start_vertex_id="v", offset=-0.5, width=80)


def test_background_opacity_is_between_0_and_1() -> None:
    assert [background(opacity=o).opacity for o in (0, 1)] == [0, 1]
    for bad in (-0.5, 1.5):
        with pytest.raises(ValidationError):
            background(opacity=bad)


def test_rejects_door_without_door_settings_and_window_with_them() -> None:
    common: dict[str, Any] = {
        "id": "o",
        "room_id": "r",
        "edge_start_vertex_id": "v",
        "offset": 0,
        "width": 80,
    }
    with pytest.raises(ValidationError, match="door settings"):
        Opening(kind="door", **common)
    with pytest.raises(ValidationError, match="door settings"):
        Opening(kind="window", door=DoorSpec(hinge="start", swing="in"), **common)


def test_rejects_empty_layouts() -> None:
    with pytest.raises(ValidationError, match="layouts\n  Tuple should have at least 1 item"):
        revalidate(full_project(), layouts=[])


def test_rejects_duplicate_ids_across_entities() -> None:
    doc = full_project()
    furniture = doc.model_dump(mode="json")
    furniture["layouts"][1]["furniture"][0]["id"] = doc.layouts[0].furniture[0].id
    vertex = doc.model_dump(mode="json")
    vertex["apartment"]["rooms"][0]["vertices"][1]["id"] = doc.apartment.rooms[0].id

    for data in (furniture, vertex):
        with pytest.raises(ValidationError, match="duplicate IDs"):
            ProjectDoc.model_validate(data)


def test_rejects_opening_on_unknown_vertex() -> None:
    data = full_project().model_dump(mode="json")
    data["apartment"]["openings"][0]["edge_start_vertex_id"] = "missing"

    with pytest.raises(ValidationError, match=r"openings\[0\]\.edge_start_vertex_id"):
        ProjectDoc.model_validate(data)


def test_rejects_opening_on_unknown_room() -> None:
    data = full_project().model_dump(mode="json")
    data["apartment"]["openings"][1]["room_id"] = "missing"

    with pytest.raises(ValidationError, match=r"openings\[1\]\.room_id"):
        ProjectDoc.model_validate(data)


def test_rejects_furniture_in_unknown_group_or_room() -> None:
    data = full_project().model_dump(mode="json")
    furniture = data["layouts"][1]["furniture"][0]
    furniture["group_id"] = "missing-group"
    furniture["room_id"] = "missing-room"

    with pytest.raises(ValidationError) as excinfo:
        ProjectDoc.model_validate(data)

    message = str(excinfo.value)
    assert "layouts[1].furniture[0].group_id" in message
    assert "layouts[1].furniture[0].room_id" in message


def test_rejects_naive_timestamps() -> None:
    with pytest.raises(ValidationError):
        revalidate(full_project(), created_at="2026-10-21T12:00:00")


def test_defaults_follow_the_spec() -> None:
    settings = ProjectSettings()
    bg = background()
    sofa = FurnitureItem(id="f", name="Sofa", shape=RectShape(width=200, depth=90), x=0, y=0)

    assert settings == ProjectSettings(
        display_unit="cm",
        grid_size=10,
        snap_enabled=True,
        default_clearance=60,
        apartment_locked=False,
    )
    assert (bg.rotation, bg.opacity, bg.visible, bg.locked) == (0, 0.5, True, True)
    assert (sofa.rotation, sofa.locked, sofa.clearance) == (0, False, None)
