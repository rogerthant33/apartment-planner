import pytest
import shapely
from shapely.geometry import Point, Polygon

from apartment_planner.geometry.labels import label_anchor, label_position
from apartment_planner.geometry.shapes import placed_polygon, room_polygon
from tests.factories import rect_item, rect_room

ROOM = room_polygon(rect_room(0, 0, 400, 300))
LABEL = (60.0, 20.0)  # width, depth in cm
CENTRE = (200.0, 150.0)


def fits(at: tuple[float, float], blocker: Polygon) -> bool:
    (x, y), (w, d) = at, LABEL
    label = shapely.box(x - w / 2, y - d / 2, x + w / 2, y + d / 2)
    return ROOM.contains(label) and not label.intersects(blocker)


def test_a_clear_label_stays_at_its_anchor() -> None:
    sofa = shapely.box(0, 0, 100, 50)

    assert label_position(ROOM, sofa, LABEL, CENTRE) == CENTRE


def test_a_covered_label_moves_to_the_nearest_clear_spot_with_a_gap() -> None:
    table = shapely.box(150, 120, 250, 180)  # over the centre

    moved = label_position(ROOM, table, LABEL, CENTRE)

    assert moved == (200, 100)  # straight up, on a 10 cm step: its bottom edge 10 cm clear


def test_labels_move_clear_of_turned_furniture() -> None:
    sofa = placed_polygon(rect_item(160, 80, x=200, y=150, rotation=37))

    moved = label_position(ROOM, sofa, LABEL, CENTRE)

    assert moved != CENTRE and fits(moved, sofa)


def test_with_no_clear_spot_the_label_covers_as_little_as_it_can() -> None:
    narrow = room_polygon(rect_room(0, 0, 100, 40))
    wardrobe = shapely.box(40, 0, 100, 40)  # leaves 40 cm of a 100 cm room clear

    x, _ = label_position(narrow, wardrobe, LABEL, (50, 20))

    assert x == 40  # as far left as it goes in 10 cm steps, at least 5 cm from the wall


@pytest.mark.parametrize(
    ("room", "blocker", "size"),
    [
        (room_polygon(rect_room(0, 0, 60, 40)), shapely.box(0, 0, 60, 40), LABEL),  # too small
        (ROOM, shapely.box(0, 0, 400, 300), (0.0, 20.0)),  # no label to place
        (ROOM, Polygon(), LABEL),  # nothing in the way
    ],
)
def test_otherwise_the_label_stays_put(
    room: Polygon, blocker: Polygon, size: tuple[float, float]
) -> None:
    assert label_position(room, blocker, size, (50, 20)) == (50, 20)


def test_an_l_shaped_rooms_anchor_is_inside_it() -> None:
    corner = Polygon([(0, 0), (300, 0), (300, 60), (60, 60), (60, 300), (0, 300)])

    assert corner.contains(Point(label_anchor(corner)))
    assert label_anchor(ROOM) == CENTRE
