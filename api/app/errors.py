import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.production_runs import ProductionRunEnqueueError
from app.services.supabase_rest import SupabaseRestError
from app.services.supabase_storage import SupabaseStorageError

logger = logging.getLogger(__name__)

DATABASE_ERROR_MESSAGE = "Arsenal could not reach the database."
STORAGE_ERROR_MESSAGE = "Arsenal could not reach file storage."


def is_duplicate_key_error(exc: SupabaseRestError) -> bool:
    return "duplicate key value" in str(exc).lower()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SupabaseRestError)
    async def handle_supabase_rest_error(
        request: Request,
        exc: SupabaseRestError,
    ) -> JSONResponse:
        logger.exception("Supabase REST error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": DATABASE_ERROR_MESSAGE},
        )

    @app.exception_handler(SupabaseStorageError)
    async def handle_supabase_storage_error(
        request: Request,
        exc: SupabaseStorageError,
    ) -> JSONResponse:
        logger.exception("Supabase Storage error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": STORAGE_ERROR_MESSAGE},
        )

    @app.exception_handler(ProductionRunEnqueueError)
    async def handle_production_run_enqueue_error(
        request: Request,
        exc: ProductionRunEnqueueError,
    ) -> JSONResponse:
        logger.exception("Production run enqueue error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Production run could not be queued. Is Redis running?",
            },
        )
