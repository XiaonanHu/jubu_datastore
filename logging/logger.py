from loguru import logger


def get_logger(name):
    """Get a logger instance for a specific module."""
    return logger.bind(name=name)
