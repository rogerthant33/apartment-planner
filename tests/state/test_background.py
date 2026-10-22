import math

import pytest

from apartment_planner.model import ProjectDoc, new_project
from apartment_planner.state.background import (
    calibrate,
    image_to_world,
    image_type,
    move_background,
    remove_background,
    set_background,
    update_background,
    world_to_image,
)
from apartment_planner.state.errors import EditError
from tests.factories import NOW


def close(p: tuple[float, float], q: tuple[float, float]) -> bool:
    return math.dist(p, q) < 1e-9


def placed(rotation: float = 0.0) -> ProjectDoc:
    """A 400 by 200 pixel image centred on (100, 50), unlocked."""
    doc, _ = set_background(new_project("Flat", now=NOW), "image/png", (400, 200), (100, 50))
    return update_background(doc, rotation=rotation)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n...", "image/png"),
        (b"\xff\xd8\xff\xe0...", "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", None),
        (b"RIFF\x00\x00\x00\x00XWMAfmt ", None),
        (b"FORM\x00\x00\x00\x00WEBPVP8 ", None),
        (b"RIFX\x00\x00\x00\x00WEBPVP8 ", None),
        (b"GIF89a", None),
    ],
)
def test_image_type_from_the_first_bytes(data: bytes, expected: str | None) -> None:
    assert image_type(data) == expected


def test_a_new_image_is_centred_unlocked_and_replaces_the_old_one() -> None:
    doc = placed()
    first = doc.background
    doc, asset_id = set_background(doc, "image/jpeg", (11, 7), (0, 0))

    bg = doc.background
    assert bg is not None and first is not None
    assert (bg.asset_id, bg.mime_type, bg.origin.x, bg.origin.y) == (
        asset_id,
        "image/jpeg",
        -5.5,
        -3.5,
    )
    assert (first.origin.x, first.origin.y, first.locked) == (-100, -50, False)
    assert image_to_world(first, (200, 100)) == (100, 50)


@pytest.mark.parametrize("rotation", [0, 90, 37])
def test_world_and_image_coordinates_round_trip(rotation: float) -> None:
    bg = update_background(placed(rotation), cm_per_pixel=2.5).background
    assert bg is not None

    assert close(world_to_image(bg, image_to_world(bg, (123.25, 45.5))), (123.25, 45.5))


def test_image_turns_clockwise_about_its_corner() -> None:
    bg = placed(90).background
    assert bg is not None

    assert close(image_to_world(bg, (10, 0)), (-100, -40))


@pytest.mark.parametrize("rotation", [0, 37])
def test_calibration_scales_about_the_first_point(rotation: float) -> None:
    doc = placed(rotation)
    before = doc.background
    assert before is not None
    a, b = image_to_world(before, (50, 30)), image_to_world(before, (250, 30))  # 200 cm apart

    doc = calibrate(doc, a, b, 350)

    bg = doc.background
    assert bg is not None
    assert bg.cm_per_pixel == pytest.approx(1.75)
    assert close(image_to_world(bg, (50, 30)), a)
    assert math.dist(image_to_world(bg, (50, 30)), image_to_world(bg, (250, 30))) == (
        pytest.approx(350)
    )


@pytest.mark.parametrize(
    ("b", "distance", "message"),
    [
        ((0.9, 0), 100, "Click two points further apart"),
        ((1, 0), 0, "Enter the real distance"),
        ((1, 0), -0.5, "Enter the real distance"),
    ],
)
def test_calibration_refuses_unusable_input(
    b: tuple[float, float], distance: float, message: str
) -> None:
    calibrate(placed(), (0, 0), (1, 0), 0.5)  # exactly 1 cm apart is enough, for any distance

    with pytest.raises(EditError, match=message):
        calibrate(placed(), (0, 0), b, distance)


def test_moving_needs_the_image_unlocked() -> None:
    doc = move_background(placed(), (10, -5))
    bg = doc.background
    assert bg is not None
    assert (bg.origin.x, bg.origin.y) == (-90, -55)

    with pytest.raises(EditError, match="locked"):
        move_background(update_background(doc, locked=True), (1, 1))


def test_edits_without_an_image_are_refused() -> None:
    doc = remove_background(placed())

    assert doc.background is None
    with pytest.raises(EditError, match="Import one first"):
        update_background(doc, opacity=1)
