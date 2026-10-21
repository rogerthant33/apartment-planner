import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from apartment_planner.canvas.view import MAX_SCALE, MIN_SCALE, PlanView
from apartment_planner.model import new_project
from apartment_planner.state.editor import EditorState
from apartment_planner.state.rooms import add_room
from tests.factories import NOW


@pytest.fixture
def view(qtbot: QtBot) -> PlanView:
    view = PlanView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    doc, _ = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    view.set_state(EditorState(doc), editable=True)
    return view


def test_zoom_and_pan_never_change_the_document(view: PlanView) -> None:
    before, revision = view.state.doc, view.state.revision

    view.zoom_by(3.0, QPoint(100, 100))
    view.pan_by(120, -40)
    view.zoom_to_fit()

    assert view.state.doc == before
    assert view.state.revision == revision


def test_zoom_keeps_the_point_under_the_cursor_in_place(view: PlanView) -> None:
    anchor = QPoint(200, 150)
    before = view.mapToScene(anchor)

    view.zoom_by(2.5, anchor)

    after = view.mapToScene(anchor)
    assert (after.x(), after.y()) == pytest.approx((before.x(), before.y()), abs=1 / view.zoom)


def test_zoom_is_limited(view: PlanView) -> None:
    view.zoom_by(1e6)
    assert view.zoom == pytest.approx(MAX_SCALE)
    view.zoom_by(1e-9)
    assert view.zoom == pytest.approx(MIN_SCALE)


def test_zoom_to_fit_shows_every_room(view: PlanView) -> None:
    view.zoom_by(10)

    view.zoom_to_fit()

    visible = view.mapToScene(view.viewport().rect()).boundingRect()
    assert visible.contains(QRectF(0, 0, 400, 300))


def test_pointer_input_arrives_in_world_cm_at_any_zoom(view: PlanView) -> None:
    view.zoom_by(2.5)
    view.set_tool("rect")
    start, end = QPointF(100, 400), QPointF(300, 550)

    viewport, left, none = view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier(0)
    QTest.mousePress(viewport, left, none, view.mapFromScene(start))
    QTest.mouseMove(viewport, view.mapFromScene(end))
    QTest.mouseRelease(viewport, left, none, view.mapFromScene(end))

    created = view.state.doc.apartment.rooms[-1]
    assert [(v.x, v.y) for v in created.vertices] == [
        (100, 400),
        (300, 400),
        (300, 550),
        (100, 550),
    ]
