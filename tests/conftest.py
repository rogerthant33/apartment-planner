import os

# Qt tests run headless on every platform.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
