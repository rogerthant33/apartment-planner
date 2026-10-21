"""Errors raised when reading or writing project files.

Every message is meant to be shown to the user as-is.
"""

from pathlib import Path


class ProjectFileError(Exception):
    """Base class for project file problems."""


class NotAProjectError(ProjectFileError):
    def __init__(self, path: Path | None = None) -> None:
        name = f'"{path.name}"' if path else "This file"
        super().__init__(f"{name} isn't an Apartment Planner project.")


class NewerVersionError(ProjectFileError):
    def __init__(self, version: int) -> None:
        super().__init__(
            f"This project was saved by a newer version of Apartment Planner (format {version}). "
            "Update the app to open it."
        )


class InvalidProjectError(ProjectFileError):
    """The file is a project, but its contents are damaged or inconsistent."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("The project file is damaged:\n" + "\n".join(problems))


class ReadError(ProjectFileError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f'Couldn\'t read "{path.name}": {reason}')
