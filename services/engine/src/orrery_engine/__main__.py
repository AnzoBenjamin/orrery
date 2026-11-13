"""Entry point: `python -m orrery_engine`."""

import logging

import structlog
import uvicorn

from orrery_engine import telemetry
from orrery_engine.app import create_app
from orrery_engine.settings import load_settings


def main() -> None:
    settings = load_settings()
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            telemetry.add_trace_ids,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )
    app = create_app(settings)
    telemetry.start(settings, app)
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104 - reachable only on the internal Docker network
        port=settings.port,
        log_level=settings.log_level,
        access_log=False,
    )


if __name__ == "__main__":
    main()
