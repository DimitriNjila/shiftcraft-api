from ...models.shift_template_model import ShiftTemplateSave, ShiftTemplateResponse
from ...services.shift_template_service import shift_template_service
from ...core.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, status

shift_template_router = APIRouter(
    prefix="/api/v1/shift-templates",
    tags=["shift-templates"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
)


@shift_template_router.get("", response_model=ShiftTemplateResponse)
def get_shift_templates(restaurant_id: str):
    """Get the saved shift templates for a restaurant."""
    result = shift_template_service.get_templates(restaurant_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No shift templates found for restaurant {restaurant_id}",
        )
    return result


@shift_template_router.put("", response_model=ShiftTemplateResponse)
def save_shift_templates(body: ShiftTemplateSave):
    """Save or overwrite the shift templates for a restaurant."""
    try:
        result = shift_template_service.upsert_templates(
            restaurant_id=body.restaurant_id,
            templates=[t.model_dump() for t in body.templates],
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save shift templates: {str(e)}",
        )
