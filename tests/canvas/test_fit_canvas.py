import pytest
from pytestqt.qtbot import QtBot

from apartment_planner.canvas.items import ClearanceItem
from apartment_planner.canvas.view import PlanView
from apartment_planner.model import RectShape, new_project
from apartment_planner.state.editor import EditorState
from apartment_planner.state.furniture import add_furniture, move_furniture, update_furniture
from apartment_planner.state.rooms import add_room
from tests.factories import NOW


@pytest.fixture
def view(qtbot: QtBot) -> PlanView:
    """A 400 by 300 cm room with a 100 by 50 desk at (100, 150) and a 40 cm square
    chair overlapping its right end."""
    doc, _ = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    doc, _ = add_furniture(doc, RectShape(width=100, depth=50), (100, 150), "Desk")
    doc, _ = add_furniture(doc, RectShape(width=40, depth=40), (160, 150), "Chair")
    view = PlanView()
    qtbot.addWidget(view)
    view.set_state(EditorState(doc), editable=True)
    return view


def ids(view: PlanView) -> list[str]:
    return [f.id for f in view.state.doc.active_layout.furniture]


def flags(view: PlanView) -> list[str | None]:
    return [item.flag for item in view.plan.furniture]


def test_findings_outline_items_and_follow_the_document(view: PlanView) -> None:
    view.refresh()
    assert flags(view) == ["collision", "collision"]

    _, chair = ids(view)
    view.state.commit(move_furniture(view.state.doc, {chair}, (100, 0)))
    view.refresh()

    assert view.findings == []
    assert flags(view) == [None, None]


def test_one_selected_item_shows_its_distance_to_each_wall(view: PlanView) -> None:
    desk, chair = ids(view)
    view.state.commit(move_furniture(view.state.doc, {chair}, (100, 0)))
    view.state.commit(move_furniture(view.state.doc, {desk}, (-50, 0)))  # flush on the left

    view.state.select({desk})
    view.refresh()

    assert sorted(r.label.text for r in view.plan.readouts) == ["125 cm", "125 cm", "300 cm"]


def test_two_selected_items_show_the_gap_between_them(view: PlanView) -> None:
    desk, chair = ids(view)
    view.state.commit(move_furniture(view.state.doc, {chair}, (37, 0)))

    view.state.select({desk, chair})
    view.refresh()

    assert [r.label.text for r in view.plan.readouts] == ["27 cm"]


def test_clearance_zones_are_drawn_only_for_items_that_set_one(view: PlanView) -> None:
    desk, _ = ids(view)
    view.state.commit(update_furniture(view.state.doc, desk, clearance=60))

    view.refresh()

    zones = [item for item in view.plan.items() if isinstance(item, ClearanceItem)]
    assert len(zones) == 1
    assert zones[0].boundingRect().width() == pytest.approx(220, abs=0.5)
