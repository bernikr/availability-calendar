import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.resources import as_file, files

from fastapi import FastAPI, Response

import frontend
from config import CONFIG, VERSION
from get_calendar import get_calendar

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001, RUF029
    logger.info("Application version %s", VERSION)
    logger.info("Running on Python %s", sys.version)
    with as_file(files("templates")) as template_dir:
        frontend.update_template_dir(template_dir)
        yield


app = FastAPI(lifespan=lifespan)


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": VERSION}


@app.get("/hc")
def healthcheck() -> Response:
    return Response("OK", media_type="text/plain")


@app.get("/{cal}.ics")
async def get_ical(cal: str, key: str = "") -> Response:
    if cal not in CONFIG.calendars:
        return Response("Not Found", status_code=404)
    keys = CONFIG.calendars[cal].key
    if keys is not None and key not in keys:
        return Response("Unauthorized", status_code=401)
    c = await get_calendar(CONFIG.calendars[cal])
    return Response(c.to_ical(), media_type="text/calendar")


app.include_router(frontend.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5000, log_level="info", reload=True)  # noqa: S104
