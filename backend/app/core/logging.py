from __future__ import annotations

import logging


LOGGER_NAME = "practice_memory"
_HANDLER_MARKER = "_practice_memory_handler"


def configure_logging(level: str) -> logging.Logger:
    numeric_level = getattr(logging, level)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(numeric_level)
    logger.propagate = False
    if not any(getattr(handler, _HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
