import structlog

NZDPU_LOGGER = "nzdpu_logger"


def get_nzdpu_logger() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(NZDPU_LOGGER)
