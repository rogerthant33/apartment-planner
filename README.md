# Apartment Planner

A private 2D apartment planner: draw your rooms with real measurements, add
doors, windows and obstacles, try out furniture layouts and see what fits.

## Running from source

Needs [uv](https://docs.astral.sh/uv/) (it installs the right Python itself).

```
uv run apartment-planner
```

## Sharing the app

Other people don't need uv, Python or the source code: they get a packaged
build that runs on its own.

### Making the build

Build on the platform you want the app for: a Windows build on Windows, a Mac
build on a Mac (PyInstaller can't cross-build). It takes a few minutes.

```
uv run python packaging/build.py
```

- **Windows:** the app is the whole folder `dist/Apartment Planner/`. It holds
  `Apartment Planner.exe` and an `_internal` folder with Python and Qt. The
  `.exe` on its own doesn't run: always share the whole folder. Right-click
  the folder → Send to → Compressed (zipped) folder to get one file to send.
- **macOS:** the app is `dist/Apartment Planner.app`. Zip it (right-click →
  Compress) to send it.

Send the zip by email, a file-sharing link or a USB stick. Rebuild and resend
it after changing the app.

### What the other person does

On Windows:

1. Download the zip and extract it: right-click → Extract All. Don't run the
   app from inside the zip, as it can't find its files there.
2. Move the extracted `Apartment Planner` folder somewhere lasting, such as
   Documents or `C:\Program Files`.
3. Open the folder and double-click `Apartment Planner.exe`. To start it more
   easily later, right-click the `.exe` → Show more options → Send to →
   Desktop (create shortcut), or pin it to Start.
4. The first time, Windows SmartScreen may say "Windows protected your PC",
   because the app isn't signed by a publisher. Click **More info** → **Run
   anyway**. It asks only once.

On macOS:

1. Double-click the zip to extract it and drag `Apartment Planner.app` into
   Applications.
2. The first time, right-click the app → Open → Open (or allow it in System
   Settings → Privacy & Security), because the build isn't signed. After that
   it opens normally.

Then, on either system:

- The start screen offers **New** to create a project. Projects are saved
  automatically as `.apartment` files in `Documents/Apartment Planner/` (the
  folder can be changed on the start screen).
- To work on the same apartment, send the `.apartment` file (File → Show in
  Folder finds it) and open it with **Open…**, or keep it in a shared cloud
  folder such as OneDrive or Dropbox. If both of you have it open at once, the
  second person is offered a read-only view or an editable copy, so neither
  overwrites the other.
- The app never goes online, and nothing is installed outside its folder
  except settings (recent files, window size) and the projects themselves.

## Development

```
uv run pytest        # tests
uv run mypy          # type-check
uv run ruff check    # lint
uv run ruff format   # format
```

Scope and design: [docs/SPEC.md](docs/SPEC.md). Working conventions:
[CLAUDE.md](CLAUDE.md).
