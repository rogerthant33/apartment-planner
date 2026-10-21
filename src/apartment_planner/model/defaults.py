from datetime import UTC, datetime

from apartment_planner.model.ids import new_id
from apartment_planner.model.project import Layout, ProjectDoc


def new_layout(name: str = "Layout 1") -> Layout:
    return Layout(id=new_id(), name=name)


def new_project(name: str, *, now: datetime | None = None) -> ProjectDoc:
    """An empty project with one layout."""
    timestamp = now if now is not None else datetime.now(UTC)
    layout = new_layout()
    return ProjectDoc(
        id=new_id(),
        name=name,
        created_at=timestamp,
        updated_at=timestamp,
        layouts=(layout,),
        active_layout_id=layout.id,
    )
