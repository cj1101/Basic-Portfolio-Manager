from __future__ import annotations

from fastapi import APIRouter

from app.errors import AppError
from app.schemas import ErrorCode, UpdateApiKeyRequest, UpdateApiKeyResponse
from app.services.env_store import EnvStoreError, get_backend_env_store

router = APIRouter(prefix="/settings", tags=["settings"])


@router.patch(
    "/api-keys",
    response_model=UpdateApiKeyResponse,
    response_model_by_alias=True,
)
async def update_api_key(body: UpdateApiKeyRequest) -> UpdateApiKeyResponse:
    store = get_backend_env_store()
    try:
        result = store.update_api_key(
            key_name=body.key_name,
            new_value=body.new_value,
            confirm_overwrite=body.confirm_overwrite,
            confirm_create=body.confirm_create,
        )
    except EnvStoreError as exc:
        raise AppError(
            ErrorCode.INTERNAL,
            "Failed to update backend/.env.",
            {"path": "backend/.env"},
        ) from exc
    return UpdateApiKeyResponse(
        updated=result.updated,
        created=result.created,
        restart_required=result.restart_required,
        requires_confirmation=result.requires_confirmation,
        confirmation_type=result.confirmation_type,  # type: ignore[arg-type]
        message=result.message,
    )


__all__ = ["router"]

