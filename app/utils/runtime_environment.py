from __future__ import annotations

import os

from app.utils.paths import AppPaths


def configure_runtime_environment(paths: AppPaths) -> None:
    """Keep application-controlled temporary data and Deno cache in AppPaths."""
    deno_cache = paths.cache_dir / "deno"
    paths.temp_dir.mkdir(parents=True, exist_ok=True)
    deno_cache.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(paths.temp_dir)
    os.environ["TMP"] = str(paths.temp_dir)
    os.environ["DENO_DIR"] = str(deno_cache)
