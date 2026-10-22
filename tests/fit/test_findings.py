from collections.abc import Sequence

import pytest

from apartment_planner.fit.findings import Finding, check_fit, doorway_zone
from apartment_planner.model import (
    Apartment,
    DoorSpec,
    FurnitureItem,
    Layout,
    Obstacle,
    Opening,
    RectShape,
    Room,
    Vertex,
)
from tests.factories import item, polygon_shape, rect_item, rect_room

ROOM = rect_room(0, 0, 400, 300, "Living room")  # walls at x=0, x=400, y=0, y=300
TOP = ROOM.vertices[0].id  # the top wall runs from (0, 0) to (400, 0)


def square(x: float, y: float, size: float = 100, clearance: float | None = None) -> FurnitureItem:
    return rect_item(size, size, x, y).evolve(clearance=clearance)


def opening(kind: str, offset: float = 200, swing: str = "in") -> Opening:
    door = DoorSpec(hinge="start", swing=swing) if kind == "door" else None  # type: ignore[arg-type]
    return Opening(
        id=f"{kind}-1",
        kind=kind,  # type: ignore[arg-type]
        room_id=ROOM.id,
        edge_start_vertex_id=TOP,
        offset=offset,
        width=80,
        door=door,
    )


def check(
    *furniture: FurnitureItem,
    rooms: Sequence[Room] = (ROOM,),
    obstacles: Sequence[Obstacle] = (),
    openings: Sequence[Opening] = (),
    depth: float = 60,
) -> list[Finding]:
    apartment = Apartment(rooms=tuple(rooms), openings=tuple(openings), obstacles=tuple(obstacles))
    return check_fit(apartment, Layout(id="l", name="L", furniture=furniture), depth)


def kinds(findings: list[Finding]) -> list[str]:
    return [f.kind for f in findings]


@pytest.mark.parametrize(
    ("x", "expected"),
    [(200, []), (199.95, []), (199.8, ["overlap"])],  # flush, a sliver, a real overlap
)
def test_furniture_overlaps_only_by_more_than_eps(x: float, expected: list[str]) -> None:
    assert kinds(check(square(100, 100), square(x, 100))) == expected


def test_overlapping_furniture_is_a_collision_naming_both() -> None:
    sofa, table = square(100, 100), square(120, 120)

    (finding,) = check(sofa, table)

    assert (finding.severity, finding.ids) == ("collision", (sofa.id, table.id))
    assert finding.message == '"Item" overlaps "Item". Move one of them.'


@pytest.mark.parametrize(("x", "expected"), [(250, []), (249.8, ["obstacle"])])
def test_furniture_against_an_obstacle(x: float, expected: list[str]) -> None:
    column = Obstacle(id="c", name="Column", shape=RectShape(width=100, depth=100), x=x, y=100)

    findings = check(square(150, 100), obstacles=[column])

    assert kinds(findings) == expected
    assert [f.message for f in findings] == ['"Item" overlaps the column. Move it.'] * len(expected)


@pytest.mark.parametrize(
    ("x", "y", "rotation", "expected"),
    [
        (50, 150, 0, []),  # flush against the left wall
        (49.8, 150, 0, ["outside"]),
        (50, 150, 90, []),
        (60, 150, 37, ["outside"]),  # a turned corner pokes through the wall
    ],
)
def test_furniture_must_stay_inside_the_rooms(
    x: float, y: float, rotation: float, expected: list[str]
) -> None:
    assert kinds(check(rect_item(100, 100, x, y, rotation))) == expected


def test_furniture_may_span_adjacent_rooms_but_not_reach_beyond_them() -> None:
    kitchen = rect_room(400, 0, 200, 300, "Kitchen")
    across = rect_item(100, 50, 400, 150)  # straddles the shared wall at x=400

    assert check(across, rooms=[ROOM, kitchen]) == []
    assert kinds(check(across)) == ["outside"]
    assert check(across, rooms=[]) == []  # nothing drawn yet


def test_furniture_in_a_door_swing_is_a_collision_and_not_also_blocking() -> None:
    door = opening("door")  # the span runs from x=160 to x=240; it hinges at x=160
    stool = rect_item(20, 20, 200, 30)  # inside the swing

    (finding,) = check(stool, openings=[door])

    assert (finding.kind, finding.ids) == ("door_swing", (stool.id, door.id))
    assert finding.message == '"Item" is in the way of the door in Living room.'


@pytest.mark.parametrize(
    ("kind", "swing", "y", "expected"),
    [
        ("door", "out", 69.8, ["doorway"]),  # the stool's top edge is 59.8 cm from the wall
        ("door", "out", 70, []),
        ("opening", "in", 69.8, ["doorway"]),
        ("window", "in", 30, []),
    ],
)
def test_furniture_in_front_of_a_doorway_or_opening_is_a_warning(
    kind: str, swing: str, y: float, expected: list[str]
) -> None:
    stool = rect_item(20, 20, 200, y)

    findings = check(stool, openings=[opening(kind, swing=swing)], depth=60)

    assert kinds(findings) == expected
    assert all(f.severity == "warning" for f in findings)


def test_doorway_zone_is_on_both_sides_of_the_wall() -> None:
    hall = rect_room(0, -200, 400, 200, "Hall")
    bench = rect_item(20, 20, 200, -30)  # in the hall, in front of the door

    (finding,) = check(bench, rooms=[ROOM, hall], openings=[opening("door")])
    assert finding.message == '"Item" blocks the doorway in Living room.'


def test_doorway_zone_on_a_sloping_wall() -> None:
    # Clockwise; the first wall runs from (100, 50) to (500, 350), a 3-4-5 slope.
    corners = [(100, 50), (500, 350), (100, 350)]
    room = Room(
        id="r",
        name="R",
        vertices=tuple(Vertex(id=f"v{i}", x=x, y=y) for i, (x, y) in enumerate(corners)),
    )
    gap = Opening(
        id="o", kind="opening", room_id="r", edge_start_vertex_id="v0", offset=100, width=80
    )

    zone = doorway_zone(room, gap, 50)

    # The span runs from (148, 86) to (212, 134); 50 cm along the inward normal
    # (-0.6, 0.8) is (-30, 40).
    assert [(round(x, 9), round(y, 9)) for x, y in zone.exterior.coords[:-1]] == [
        (178, 46),
        (242, 94),
        (182, 174),
        (118, 126),
    ]


@pytest.mark.parametrize(("depth", "blocked"), [(0.5, True), (0, False), (-0.5, False)])
def test_doorways_are_checked_only_with_a_positive_depth(depth: float, blocked: bool) -> None:
    stool = rect_item(20, 20, 200, 10.2)  # 0.2 cm from the wall, in front of the opening
    window = opening("window", offset=50)  # first: windows are skipped, not the end of the list

    findings = check(stool, openings=[window, opening("opening")], depth=depth)

    assert [f.message for f in findings] == ['"Item" blocks the opening in Living room.'] * blocked


@pytest.mark.parametrize(("gap", "expected"), [(49.85, ["clearance"]), (49.95, [])])
def test_clearance_counts_only_when_closer_than_it_by_eps(gap: float, expected: list[str]) -> None:
    desk = square(150, 150, clearance=50)
    chair = square(250 + gap, 150)

    assert kinds(check(chair, desk)) == expected  # the chair first: it has no clearance
    assert check(square(150, 150), chair) == []  # no clearance set


def test_clearance_limit_itself_is_not_too_close() -> None:
    # 50.1 less EPS is exactly 50.0 in floating point, so both gaps sit on the limit.
    desk = square(100, 150, clearance=50.1)  # 50 cm from the left wall
    chair = square(250, 150)  # 50 cm from the desk

    assert check(desk, chair) == []


def test_clearance_is_reported_once_per_pair() -> None:
    desk = square(150, 150, clearance=50)
    chair = square(260, 150, clearance=50)
    column = Obstacle(id="c", name="Column", shape=RectShape(width=10, depth=10), x=150, y=215)

    findings = check(desk, chair, obstacles=[column])

    assert [f.ids for f in findings] == [(desk.id, chair.id), (desk.id, "c")]
    assert findings[1].message == '"Column" is within the 50 cm clearance of "Item".'


def test_clearance_from_walls() -> None:
    near = square(99.85, 150, clearance=50)  # its left edge is 49.85 cm from the wall

    (finding,) = check(near)

    assert (finding.ids, finding.message) == (
        (near.id,),
        'A wall is within the 50 cm clearance of "Item".',
    )
    assert check(square(99.95, 150, clearance=50)) == []


def test_overlapping_items_are_not_also_too_close() -> None:
    assert kinds(check(square(150, 150, clearance=50), square(200, 150))) == ["overlap"]


@pytest.mark.parametrize(("x", "expected"), [(400, []), (399, ["rooms_overlap"])])
def test_rooms_may_share_walls_but_not_overlap(x: float, expected: list[str]) -> None:
    kitchen = rect_room(x, 0, 200, 300, "Kitchen")

    findings = check(rooms=[ROOM, kitchen])

    assert kinds(findings) == expected
    assert [f.message for f in findings] == [
        "Living room and Kitchen overlap. Move a corner so they only share walls."
    ] * len(expected)


def test_invalid_shapes_are_reported_and_left_out_of_other_checks() -> None:
    # It crosses itself, and its last edge is too short.
    bow_tie = item(polygon_shape((0, 0), (100, 100), (100, 0), (0, 100), (0, 0.5)), 150, 150)
    sofa, table = square(150, 150), square(160, 160)  # both overlap the bow tie too

    findings = check(bow_tie, sofa, table)

    assert [(f.kind, f.ids) for f in findings] == [
        ("overlap", (sofa.id, table.id)),  # a collision, so it comes first
        ("invalid_shape", (bow_tie.id,)),
    ]
    assert findings[1].message == (
        '"Item" can\'t be checked: Edge 5 is 0.50 cm long; edges must be at least 1 cm.'
    )


def test_invalid_rooms_are_reported_and_their_walls_left_out() -> None:
    # Clockwise overall, but the outline crosses itself, and its last edge is too short.
    corners = [(0, 0), (400, 0), (400, 300), (300, 300), (300, -100), (0, 300), (0, 0.5)]
    crossed = Room(
        id="x",
        name="Hall",
        vertices=tuple(Vertex(id=f"v{i}", x=x, y=y) for i, (x, y) in enumerate(corners)),
    )
    door = opening("door").evolve(room_id="x", edge_start_vertex_id="v0")

    findings = check(square(200, 100, clearance=50), rooms=[crossed], openings=[door])

    assert [(f.kind, f.ids) for f in findings] == [("invalid_shape", ("x",))]
    assert findings[0].message == (
        "Hall can't be checked: Edge 7 is 0.50 cm long; edges must be at least 1 cm."
    )


def test_collisions_come_before_warnings() -> None:
    bow_tie = item(polygon_shape((0, 0), (100, 100), (100, 0), (0, 100)))  # a warning, found first

    findings = check(bow_tie, square(500, 150))  # outside the room: a collision

    assert [f.severity for f in findings] == ["collision", "warning"]
