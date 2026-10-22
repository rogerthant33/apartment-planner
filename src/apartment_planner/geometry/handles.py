"""Transform handles for furniture and obstacles: where they are, and what dragging
them does. All in world cm; the canvas draws and hit-tests them.
"""

import math
from enum import StrEnum

from apartment_planner.geometry.constants import MIN_EDGE_LENGTH
from apartment_planner.geometry.shapes import shape_outline
from apartment_planner.geometry.transform import XY, local_to_world, world_to_local
from apartment_planner.model import EllipseShape, Placed, RectShape, Shape

ROTATION_STEP = 15.0  # degrees the rotate handle snaps to


class Handle(StrEnum):
    """Resize handles by compass direction in the item's own frame, plus rotate."""

    N = "n"
    NE = "ne"
    E = "e"
    SE = "se"
    S = "s"
    SW = "sw"
    W = "w"
    NW = "nw"
    ROTATE = "rotate"


# Where each resize handle sits on the local box, as fractions from -1 to 1.
_SIDES: dict[Handle, tuple[int, int]] = {
    Handle.N: (0, -1),
    Handle.NE: (1, -1),
    Handle.E: (1, 0),
    Handle.SE: (1, 1),
    Handle.S: (0, 1),
    Handle.SW: (-1, 1),
    Handle.W: (-1, 0),
    Handle.NW: (-1, -1),
}


def box_size(shape: Shape) -> XY | None:
    """Width and depth of a resizable shape, or None for polygons (edited by corner)."""
    match shape:
        case RectShape(width=w, depth=d):
            return (w, d)
        case EllipseShape(rx=rx, ry=ry):
            return (2 * rx, 2 * ry)
        case _:
            return None


def with_box_size(shape: Shape, width: float, depth: float) -> Shape:
    match shape:
        case RectShape():
            return shape.evolve(width=width, depth=depth)
        case EllipseShape():
            return shape.evolve(rx=width / 2, ry=depth / 2)
        case _:
            raise TypeError(f"{shape.type} shapes have no box size")


def handle_positions(item: Placed, rotate_offset: float) -> dict[Handle, XY]:
    """World positions of an item's handles. The rotate handle sits `rotate_offset` cm
    beyond the top edge."""
    size = box_size(item.shape)
    origin = (item.x, item.y)
    handles: dict[Handle, XY] = {}
    if size is not None:
        hw, hd = size[0] / 2, size[1] / 2
        for handle, (sx, sy) in _SIDES.items():
            handles[handle] = local_to_world((sx * hw, sy * hd), origin, item.rotation)
        top = -hd
    else:
        top = min(y for _, y in shape_outline(item.shape))
    handles[Handle.ROTATE] = local_to_world((0, top - rotate_offset), origin, item.rotation)
    return handles


def resized(item: Placed, handle: Handle, world: XY) -> tuple[Shape, XY]:
    """The shape and origin after dragging a resize handle to `world`.

    The opposite side or corner stays put; sizes never go below MIN_EDGE_LENGTH.
    """
    size = box_size(item.shape)
    # pragma below: Handle members are singletons, so `==` behaves like `is`.
    if size is None or handle is Handle.ROTATE:  # pragma: no mutate
        raise ValueError(f"{handle} doesn't resize {item.shape.type} shapes")
    sx, sy = _SIDES[handle]
    hw, hd = size[0] / 2, size[1] / 2
    px, py = world_to_local(world, (item.x, item.y), item.rotation)
    # The fixed edge in local coordinates, and the new extent towards the handle.
    width, centre_x = _span(sx, hw, px)
    depth, centre_y = _span(sy, hd, py)
    centre = local_to_world((centre_x, centre_y), (item.x, item.y), item.rotation)
    return with_box_size(item.shape, width, depth), centre


def _span(side: int, half: float, pointer: float) -> tuple[float, float]:
    """New length and centre along one axis. `side` is -1, 0 or 1 (0: unchanged)."""
    if side == 0:
        return 2 * half, 0.0
    fixed = -side * half
    # `side` first, so a `/` mutant isn't equivalent (dividing by ±1 is multiplying).
    length = max(side * (pointer - fixed), MIN_EDGE_LENGTH)
    return length, fixed + side * length / 2


def rotation_towards(origin: XY, world: XY, snap: bool) -> float:
    """The rotation that points the item's top edge at `world`, snapped to 15° steps."""
    degrees = math.degrees(math.atan2(world[0] - origin[0], origin[1] - world[1]))
    if snap:
        degrees = round(degrees / ROTATION_STEP) * ROTATION_STEP
    return degrees % 360.0
