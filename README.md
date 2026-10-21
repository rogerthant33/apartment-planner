# Apartment Planner

A private 2D apartment planner: draw your rooms with real measurements, add
doors, windows and obstacles, try out furniture layouts and see what fits.

## Running from source

Needs [uv](https://docs.astral.sh/uv/) (it installs the right Python itself).

```
uv run apartment-planner
```

## Development

```
uv run pytest        # tests
uv run mypy          # type-check
uv run ruff check    # lint
uv run ruff format   # format
```

Scope and design: [docs/SPEC.md](docs/SPEC.md). Working conventions:
[CLAUDE.md](CLAUDE.md).
