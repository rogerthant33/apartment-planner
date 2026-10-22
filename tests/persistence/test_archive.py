import io
import json
import zipfile
from typing import Any

import pytest

from apartment_planner.persistence.archive import ProjectFile, asset_path, decode, encode
from apartment_planner.persistence.errors import (
    InvalidProjectError,
    NewerVersionError,
    NotAProjectError,
)
from tests.factories import full_project

IMAGE = b"\x89PNG\r\n\x1a\nimage bytes"


def project() -> ProjectFile:
    doc = full_project()
    assert doc.background is not None
    return ProjectFile(doc, {doc.background.asset_id: IMAGE})


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def payload_bytes(**changes: Any) -> bytes:
    payload = json.loads(zipfile.ZipFile(io.BytesIO(encode(project()))).read("project.json"))
    payload.update(changes)
    return zip_bytes({"project.json": json.dumps(payload).encode()})


def test_round_trip_keeps_document_and_image_bytes() -> None:
    original = project()

    restored = decode(encode(original))

    assert restored == original


def test_project_json_is_pretty_and_compressed_and_images_are_stored() -> None:
    original = project()
    assert original.doc.background is not None

    archive = zipfile.ZipFile(io.BytesIO(encode(original)))
    image = archive.getinfo(asset_path(original.doc.background.asset_id, "image/png"))
    text = archive.read("project.json").decode()

    assert archive.getinfo("project.json").compress_type == zipfile.ZIP_DEFLATED
    assert image.compress_type == zipfile.ZIP_STORED
    assert text.startswith('{\n  "format": "apartment-planner",\n  "schema_version": 1,\n')


@pytest.mark.parametrize(
    "data",
    [
        b"not a zip",
        zip_bytes({"other.json": b"{}"}),
        zip_bytes({"project.json": b"\xff\xfe"}),
        zip_bytes({"project.json": b"[1, 2]"}),
    ],
    ids=["not-zip", "no-project-json", "not-utf8", "not-object"],
)
def test_rejects_files_that_are_not_projects(data: bytes) -> None:
    with pytest.raises(NotAProjectError):
        decode(data)


def test_rejects_other_formats() -> None:
    with pytest.raises(NotAProjectError):
        decode(payload_bytes(format="something-else"))


def test_refuses_newer_schema_versions() -> None:
    with pytest.raises(NewerVersionError, match="newer version"):
        decode(payload_bytes(schema_version=2))


@pytest.mark.parametrize("version", [0, "1", True, None])
def test_rejects_malformed_schema_versions(version: object) -> None:
    with pytest.raises(InvalidProjectError, match="schema_version"):
        decode(payload_bytes(schema_version=version))


def test_rejects_missing_project() -> None:
    with pytest.raises(InvalidProjectError, match="project is missing"):
        decode(payload_bytes(project=None))


def test_validation_errors_name_the_failing_field() -> None:
    doc = full_project().model_dump(mode="json")
    doc["apartment"]["rooms"][0]["vertices"] = doc["apartment"]["rooms"][0]["vertices"][:2]

    with pytest.raises(InvalidProjectError) as excinfo:
        decode(payload_bytes(project=doc))

    assert excinfo.value.problems[0].startswith("apartment.rooms.0.vertices: ")


def test_rejects_missing_image() -> None:
    # payload_bytes() repackages project.json on its own, without the image.
    with pytest.raises(InvalidProjectError, match=r"missing image file assets/\w+\.png"):
        decode(payload_bytes())
