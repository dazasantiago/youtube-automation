"""One-time script: resolve channel handles → IDs and populate yt_channels table."""

from __future__ import annotations

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    from content_intel.db import init_db
    from content_intel.sources.youtube import bootstrap_channels

    init_db()
    bootstrap_channels()


if __name__ == "__main__":
    main()
