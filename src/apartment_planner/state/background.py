"""The background floor-plan image: placing, moving and calibrating it. See
docs/SPEC.md §10.

An image pixel (px, py) is at world `origin + rotate((px, py) * cm_per_pixel)`.
"""

import math
from typing import Any, Literal

from apartment_planner.geometry.constants import MIN_EDGE_LENGTH
from apartment_planner.geometry.transform import XY, rotate
from apartment_planner.model import BackgroundImage, Point, ProjectDoc, new_id
from apartment_planner.state.errors import EditError

MimeType = Literal["image/png", "image/jpeg", "image/webp"]

DEFAULT_CM_PER_PIXEL = 1.0  # until it's calibrated


def image_type(data: bytes) -> MimeType | None:
    """The image format, from the file's first bytes; None if it isn't one we take."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def image_to_world(bg: BackgroundImage, pixel: XY) -> XY:
    dx, dy = rotate((pixel[0] * bg.cm_per_pixel, pixel[1] * bg.cm_per_pixel), bg.rotation)
    return (bg.origin.x + dx, bg.origin.y + dy)


def world_to_image(bg: BackgroundImage, world: XY) -> XY:
    dx, dy = rotate((world[0] - bg.origin.x, world[1] - bg.origin.y), -bg.rotation)
    return (dx / bg.cm_per_pixel, dy / bg.cm_per_pixel)


def set_background(
    doc: ProjectDoc, mime_type: MimeType, size: tuple[int, int], centre: XY
) -> tuple[ProjectDoc, str]:
    """A new background image of `size` pixels, centred on `centre`, replacing any
    other. Returns the document and the new image's asset ID."""
    asset_id = new_id()
    # pragma below: the default scale is 1, so dividing by it or raising to it is the same.
    width, height = (n * DEFAULT_CM_PER_PIXEL for n in size)  # pragma: no mutate
    background = BackgroundImage(
        asset_id=asset_id,
        mime_type=mime_type,
        origin=Point(x=centre[0] - width / 2, y=centre[1] - height / 2),
        cm_per_pixel=DEFAULT_CM_PER_PIXEL,
        locked=False,  # it still has to be calibrated and moved into place
    )
    return doc.evolve(background=background), asset_id


def update_background(doc: ProjectDoc, **changes: Any) -> ProjectDoc:
    """Change the background image. A rotation turns it about its top-left corner."""
    return doc.evolve(background=_background(doc).evolve(**changes))


def move_background(doc: ProjectDoc, delta: XY) -> ProjectDoc:
    bg = _background(doc)
    if bg.locked:
        raise EditError("The background image is locked. Unlock it to move it.")
    origin = Point(x=bg.origin.x + delta[0], y=bg.origin.y + delta[1])
    return doc.evolve(background=bg.evolve(origin=origin))


def calibrate(doc: ProjectDoc, a: XY, b: XY, distance: float) -> ProjectDoc:
    """Scale the image so the points clicked at world `a` and `b` are `distance` cm
    apart. The image stays put at `a`."""
    bg = _background(doc)
    if not distance > 0:
        raise EditError("Enter the real distance between the two points, such as 3.5 m.")
    clicked = math.dist(a, b)
    if clicked < MIN_EDGE_LENGTH:
        raise EditError("Click two points further apart on the image, then try again.")
    scale = bg.cm_per_pixel * distance / clicked
    pixel = world_to_image(bg, a)
    dx, dy = rotate((pixel[0] * scale, pixel[1] * scale), bg.rotation)
    origin = Point(x=a[0] - dx, y=a[1] - dy)
    return doc.evolve(background=bg.evolve(cm_per_pixel=scale, origin=origin))


def remove_background(doc: ProjectDoc) -> ProjectDoc:
    return doc.evolve(background=None)


def _background(doc: ProjectDoc) -> BackgroundImage:
    if doc.background is None:
        raise EditError("There is no background image. Import one first.")
    return doc.background
