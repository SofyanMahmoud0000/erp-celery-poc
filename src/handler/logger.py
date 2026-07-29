"""
Local stand-in for `backend_common.Logger`.

The real erp-managment service depends on the private git package
`backend-common` (git@github.com:settle-payments/be-package.git) for its
`Logger`/`BucketHandler` classes. That repo isn't reachable from this
sandbox, so this POC uses a minimal local stub with the same call surface
(`.debug()/.info()/.warning()/.error()`) so the rest of the code can be
copied over unchanged.
"""
import logging
import sys


class Logger:
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
            )
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)
