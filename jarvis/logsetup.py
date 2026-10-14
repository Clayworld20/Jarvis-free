import logging
from logging.handlers import RotatingFileHandler

from . import paths
from .events import BusLogHandler, EventBus


def setup_logging(bus: EventBus, console: bool = True, debug: bool = False) -> logging.Logger:
    paths.ensure_dirs()
    logger = logging.getLogger("jarvis")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")

    file_handler = RotatingFileHandler(paths.LOG_DIR / "jarvis.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    bus_handler = BusLogHandler(bus)
    logger.addHandler(bus_handler)

    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        logger.addHandler(stream)
    logger.propagate = False
    return logger
