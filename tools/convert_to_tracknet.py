"""Backward-compatible entry point.

The implementation moved to ``app/tools/convert_to_tracknet.py`` so it is
bundled with the installed application (``tracknet-prepper-cli
convert-tracknet``). This script keeps ``python tools/convert_to_tracknet.py``
working from a source checkout.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.convert_to_tracknet import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
