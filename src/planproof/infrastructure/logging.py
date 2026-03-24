"""Structured JSON logging configuration using structlog.

Provides a consistent logging setup across all PlanProof modules.
All log entries are JSON-formatted for easy ingestion into log aggregators
and for structured querying during debugging.
"""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Initialise structlog with JSON output and stdlib integration.

    Should be called once at application startup (e.g. in ``bootstrap.py``).

    Parameters
    ----------
    log_level:
        Minimum severity level (``"DEBUG"``, ``"INFO"``, ``"WARNING"``, etc.).
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound logger scoped to *name*.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.
    """
    return structlog.get_logger(name)
