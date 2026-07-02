from __future__ import annotations

import sys

from craftsman.cli import main


if __name__ == "__main__":
    sys.argv = ["craftsman", "serve"]
    main()
