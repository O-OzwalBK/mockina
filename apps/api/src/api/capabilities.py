"""The public route that tells a browser what this server offers."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependencies import get_api_settings
from api.product_models import Capabilities, current_limits
from api.settings import ApiSettings

router = APIRouter(prefix="/v1", tags=["capabilities"])


@router.get(
    "/capabilities",
    summary="Read Server Capabilities",
    response_description="Retention, optional features and the limits the server enforces.",
    response_model=Capabilities,
)
def read_capabilities(settings: Annotated[ApiSettings, Depends(get_api_settings)]) -> Capabilities:
    """Report what this server can do and how much input it accepts.

    Anyone may call this, with or without an identity, so a browser can adapt its screens
    (for example, hide a feature the server lacks) before it creates an identity.
    """
    return Capabilities(
        anonymous_retention_days=settings.anon_retention_days,
        hosted_stt=False,
        dev_routes=settings.dev_routes,
        limits=current_limits(),
    )
