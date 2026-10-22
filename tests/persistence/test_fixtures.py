"""Every file format version ever released must keep opening. See the schema-change skill."""

import hashlib
from pathlib import Path

import pytest

from apartment_planner.model import CURRENT_SCHEMA_VERSION
from apartment_planner.persistence.files import read_project

FIXTURES = Path(__file__).parent.parent / "fixtures"
FIXTURE_FILES = sorted(FIXTURES.glob("*.apartment"))


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name)
def test_fixture_loads_with_the_current_loader(path: Path) -> None:
    read_project(path)


def test_every_schema_version_has_a_fixture() -> None:
    # Fixtures are named v<schema version>_<description>.apartment.
    versions = {int(p.name.split("_")[0].removeprefix("v")) for p in FIXTURE_FILES}

    assert versions == set(range(1, CURRENT_SCHEMA_VERSION + 1))


def test_v1_fixture_keeps_its_content() -> None:
    project = read_project(FIXTURES / "v1_full.apartment").project
    doc = project.doc
    furniture = [f for layout in doc.layouts for f in layout.furniture]

    assert [o.kind for o in doc.apartment.openings] == ["door", "window"]
    assert [o.name for o in doc.apartment.obstacles] == ["Column"]
    assert sorted(f.shape.type for f in furniture) == ["ellipse", "polygon", "rect"]
    assert furniture[0].meta is not None
    assert furniture[0].meta.product == "Söderhamn 3-seat"
    assert doc.background is not None
    image = project.assets[doc.background.asset_id]
    assert hashlib.sha256(image).hexdigest().startswith("33d9ef587fa6")
