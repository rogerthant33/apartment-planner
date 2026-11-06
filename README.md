# Apartment Planner

A private 2D apartment planner: draw your rooms with real measurements, add
doors, windows and obstacles, try out furniture layouts and see what fits.

## Running from source

Needs [uv](https://docs.astral.sh/uv/).

```
uv run apartment-planner
```

## Sharing the app

Build on the system you're building for (a Windows build on Windows, a Mac
build on a Mac):

```
uv run python packaging/build.py
```

- **Windows:** zip the whole `dist/Apartment Planner/` folder, not just the
  `.exe`, which can't run without the rest. To run it, extract the zip and open
  `Apartment Planner.exe`. If SmartScreen warns, click **More info** → **Run
  anyway**.
- **macOS:** zip `dist/Apartment Planner.app`. To run it, extract the zip and
  drag the app into Applications. The first time, right-click it → **Open** →
  **Open**, because the build isn't signed.

Projects are saved as `.apartment` files in `Documents/Apartment Planner/`.
To work on one together, send the file or keep it in a shared cloud folder.

## Development

```
uv run pytest        # tests
uv run mypy          # type-check
uv run ruff check    # lint
uv run ruff format   # format
```

Scope and design: [docs/SPEC.md](docs/SPEC.md). Working conventions:
[CLAUDE.md](CLAUDE.md).
