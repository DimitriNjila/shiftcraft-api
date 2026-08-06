import logging

from ...models.shift_template_model import ShiftTemplateSave, ShiftTemplateResponse
from ...models.template_import_model import (
    TemplateImportConfirmRequest,
    TemplateImportPreviewResponse,
)
from ...services.ai_service import AIServiceUnavailableError
from ...services.shift_template_service import shift_template_service
from ...services.template_import_service import template_import_service
from ...core.auth import get_current_user
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

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


@shift_template_router.post("/import/parse", response_model=TemplateImportPreviewResponse)
async def parse_template_import(file: UploadFile = File(...)):
    """
    Parse an uploaded CSV/Excel file into a preview of shift templates.

    Does NOT save anything — returns best-guess column mapping and each row
    flagged with any validation errors/warnings, for the frontend to show a
    confirmation UI before calling /import/confirm.
    """
    file_bytes = await file.read()
    try:
        rows, column_mapping = template_import_service.parse_template_file(
            file_bytes, file.filename
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("POST /shift-templates/import/parse failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while parsing the file.",
        )

    validated_rows = template_import_service.validate_parsed_templates(rows)
    return {
        "column_mapping": column_mapping,
        "rows": validated_rows,
        "valid_count": sum(1 for r in validated_rows if r["is_valid"]),
        "error_count": sum(1 for r in validated_rows if not r["is_valid"]),
    }


@shift_template_router.post("/import/image/parse", response_model=TemplateImportPreviewResponse)
async def parse_template_image_import(file: UploadFile = File(...)):
    """
    Parse an uploaded photo/screenshot of a schedule into a preview of shift
    templates via vision AI.

    Uses the exact same preview shape as /import/parse (CSV/Excel) — rows are
    flagged with confidence + validation errors/warnings, nothing is saved.
    Save confirmed rows via the same /import/confirm endpoint.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected an image file, got content type {file.content_type!r}",
        )

    image_bytes = await file.read()
    try:
        rows = template_import_service.parse_template_image(
            image_bytes, file.content_type
        )
    except AIServiceUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except ValueError as e:
        # At this point the file type is already known-good, so a ValueError
        # here means the vision model's response couldn't be parsed — an
        # upstream failure, not a bad request.
        logger.error("Vision model response unusable for image import: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision AI returned an unexpected response. Please try again.",
        )
    except Exception as e:
        logger.exception("POST /shift-templates/import/image/parse failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision AI analysis failed. Please try again later.",
        )

    validated_rows = template_import_service.validate_parsed_templates(rows)
    return {
        "column_mapping": {},
        "rows": validated_rows,
        "valid_count": sum(1 for r in validated_rows if r["is_valid"]),
        "error_count": sum(1 for r in validated_rows if not r["is_valid"]),
    }


@shift_template_router.post("/import/confirm", response_model=ShiftTemplateResponse)
def confirm_template_import(body: TemplateImportConfirmRequest):
    """Save confirmed rows from a previous /import/parse preview."""
    if not body.rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No rows to import",
        )
    try:
        result = template_import_service.save_templates_batch(
            restaurant_id=body.restaurant_id,
            rows=[r.model_dump() for r in body.rows],
        )
        return result
    except Exception as e:
        logger.exception("POST /shift-templates/import/confirm failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save imported templates: {str(e)}",
        )
