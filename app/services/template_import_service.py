import io
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..core.constants import DayOfWeek
from .ai_service import get_ai_service
from .shift_template_service import ShiftTemplateService

logger = logging.getLogger(__name__)

# Best-guess header -> normalized field mapping. Matched against a lowercased,
# whitespace/punctuation-stripped version of each source column header.
FIELD_SYNONYMS: Dict[str, List[str]] = {
    "day_of_week": ["dayofweek", "day", "weekday", "dow"],
    "start_time": ["starttime", "start", "from", "begins", "opens", "shiftstart"],
    "end_time": ["endtime", "end", "to", "finishes", "closes", "shiftend"],
    "role": ["role", "position", "job", "jobtitle", "employeerole"],
    "count": ["count", "headcount", "qty", "quantity", "needed", "numemployees", "employeesneeded"],
}

_DAY_NAME_TO_ISO = {name.lower(): member.value for name, member in DayOfWeek.__members__.items()}
_DAY_ABBR_TO_ISO = {name.lower()[:3]: member.value for name, member in DayOfWeek.__members__.items()}

_TIME_FORMATS = ["%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I%p", "%I %p"]

REQUIRED_FIELDS = ("day_of_week", "start_time", "end_time", "role")


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


class TemplateImportService:
    """Service for parsing, validating, and saving imported shift templates."""

    def __init__(self, shift_template_service: Optional[ShiftTemplateService] = None):
        self.shift_template_service = shift_template_service or ShiftTemplateService()

    # === Parsing ===

    def parse_template_file(
        self, file_bytes: bytes, filename: str
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Parse an uploaded CSV or Excel file into raw row dicts, using a
        best-guess mapping from source columns to normalized fields.

        Does NOT save anything or validate business rules — see
        validate_parsed_templates for that.

        Args:
            file_bytes: Raw file content
            filename: Original filename, used to pick the CSV vs Excel parser

        Returns:
            (rows, column_mapping) where rows is a list of dicts with keys
            from REQUIRED_FIELDS + "count" (raw/untyped values, still strings)
            and column_mapping maps normalized_field -> source column header
            (only for fields a column was found for).

        Raises:
            ValueError: If the file can't be parsed at all (corrupt, wrong format)
        """
        lower_name = (filename or "").lower()
        try:
            if lower_name.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
            elif lower_name.endswith(".xlsx") or lower_name.endswith(".xls"):
                df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, engine="openpyxl")
                df = df.fillna("")
            else:
                raise ValueError(
                    f"Unsupported file type: {filename!r}. Expected .csv or .xlsx"
                )
        except ValueError:
            raise
        except Exception as e:
            logger.error("Failed to parse template file %s: %s", filename, e)
            raise ValueError(f"Could not parse file: {e}") from e

        # Drop fully-empty rows (common in exported spreadsheets)
        df = df[~(df.apply(lambda row: all(str(v).strip() == "" for v in row), axis=1))]

        column_mapping = self._guess_column_mapping(list(df.columns))

        rows: List[Dict[str, Any]] = []
        for _, series in df.iterrows():
            row = {}
            for field, source_col in column_mapping.items():
                row[field] = str(series.get(source_col, "")).strip()
            rows.append(row)

        logger.info(
            "Parsed %d rows from %s, mapped columns=%s",
            len(rows),
            filename,
            column_mapping,
        )
        return rows, column_mapping

    @staticmethod
    def _guess_column_mapping(columns: List[str]) -> Dict[str, str]:
        """Best-guess match each normalized field to a source column header."""
        normalized_columns = {col: _normalize_header(col) for col in columns}
        mapping: Dict[str, str] = {}

        for field, synonyms in FIELD_SYNONYMS.items():
            for col, normalized in normalized_columns.items():
                if normalized in synonyms:
                    mapping[field] = col
                    break
            else:
                # Fallback: substring match (e.g. header "Day of Week (1-7)")
                for col, normalized in normalized_columns.items():
                    if any(syn in normalized for syn in synonyms):
                        mapping[field] = col
                        break

        return mapping

    def parse_template_image(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> List[Dict[str, Any]]:
        """
        Extract candidate shift templates from a photo/screenshot via vision AI.

        Does NOT save anything. Returns raw rows shaped exactly like
        parse_template_file's output (plus a "confidence" flag), so callers
        run them through the same validate_parsed_templates / confirm flow
        used by CSV/Excel import.

        Args:
            image_bytes: Raw image content
            mime_type: Image MIME type (e.g. "image/jpeg", "image/png")

        Returns:
            List of raw row dicts with a "confidence" of "low" (the model
            flagged at least one field as unclear) or "high".

        Raises:
            ValueError: If the file isn't an image, or the vision model's
                        response can't be parsed
            AIServiceUnavailableError: If GROQ_API_KEY isn't configured
        """
        if not mime_type or not mime_type.startswith("image/"):
            raise ValueError(f"Expected an image file, got content type {mime_type!r}")

        ai = get_ai_service()
        raw_shifts = ai.analyze_image_for_templates(image_bytes, mime_type)

        rows = []
        for raw in raw_shifts:
            fields = {
                "day_of_week": raw.get("day_of_week"),
                "start_time": raw.get("start_time"),
                "end_time": raw.get("end_time"),
                "role": raw.get("role"),
                "count": raw.get("count"),
            }
            confidence = "low" if any(v is None for v in fields.values()) else "high"
            rows.append({**{k: "" if v is None else str(v) for k, v in fields.items()}, "confidence": confidence})

        logger.info("Parsed %d rows from image (mime=%s)", len(rows), mime_type)
        return rows

    # === Validation ===

    def validate_parsed_templates(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate and normalize each parsed row.

        Args:
            rows: Raw rows from parse_template_file (or image parsing in Phase 4)

        Returns:
            List of row dicts shaped like ParsedTemplateRow (row_number,
            day_of_week, start_time, end_time, role, count, errors, warnings,
            is_valid). Never raises — invalid rows are flagged, not dropped,
            so the frontend preview can show every row.
        """
        validated = []
        for i, raw in enumerate(rows, start=1):
            errors: List[str] = []
            warnings: List[str] = []
            confidence = raw.get("confidence")  # set by image import only; None for file import

            day_of_week = self._parse_day_of_week(raw.get("day_of_week"))
            if day_of_week is None:
                errors.append("day_of_week is missing or not recognized (expected 1-7 or a weekday name)")

            start_time = self._parse_time(raw.get("start_time"))
            if start_time is None:
                errors.append("start_time is missing or not a recognized time format")

            end_time = self._parse_time(raw.get("end_time"))
            if end_time is None:
                errors.append("end_time is missing or not a recognized time format")

            if start_time and end_time and start_time >= end_time:
                errors.append("end_time must be after start_time")

            role = str(raw.get("role") or "").strip()
            if not role:
                errors.append("role is required")

            count_raw = str(raw.get("count") or "").strip()
            count: Optional[int] = None
            if not count_raw:
                count = 1
                warnings.append("count not specified, defaulted to 1")
            else:
                try:
                    count = int(float(count_raw))
                    if count < 1:
                        errors.append("count must be at least 1")
                except ValueError:
                    errors.append(f"count {count_raw!r} is not a number")

            validated.append(
                {
                    "row_number": i,
                    "day_of_week": day_of_week,
                    "start_time": start_time,
                    "end_time": end_time,
                    "role": role or None,
                    "count": count,
                    "confidence": confidence,
                    "errors": errors,
                    "warnings": warnings,
                    "is_valid": len(errors) == 0,
                }
            )

        logger.info(
            "Validated %d rows: %d valid, %d with errors",
            len(validated),
            sum(1 for r in validated if r["is_valid"]),
            sum(1 for r in validated if not r["is_valid"]),
        )
        return validated

    @staticmethod
    def _parse_day_of_week(value: Any) -> Optional[int]:
        if value is None:
            return None
        text = str(value).strip().lower()
        if not text:
            return None

        # Numeric (1-7, ISO 8601: Monday=1)
        try:
            num = int(float(text))
            if 1 <= num <= 7:
                return num
            return None
        except ValueError:
            pass

        if text in _DAY_NAME_TO_ISO:
            return _DAY_NAME_TO_ISO[text]
        if text[:3] in _DAY_ABBR_TO_ISO:
            return _DAY_ABBR_TO_ISO[text[:3]]
        return None

    @staticmethod
    def _parse_time(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().upper().replace(".", "")
        if not text:
            return None

        for fmt in _TIME_FORMATS:
            try:
                return datetime.strptime(text, fmt).strftime("%H:%M:%S")
            except ValueError:
                continue
        return None

    # === Saving ===

    def save_templates_batch(
        self, restaurant_id: str, rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Save confirmed rows for a restaurant.

        The shift_templates table stores one JSONB array per restaurant, so
        "batch insert" here means: merge the confirmed rows into the existing
        array and upsert the whole thing — reusing ShiftTemplateService's
        existing on_conflict=restaurant_id upsert rather than a new table.

        Args:
            restaurant_id: Restaurant to save templates for
            rows: Confirmed template dicts (day_of_week, start_time, end_time,
                  role, count) — already pydantic-validated by the router

        Returns:
            The saved template record (existing + newly imported templates)
        """
        existing = self.shift_template_service.get_templates(restaurant_id)
        existing_templates = existing["templates"] if existing else []

        logger.info(
            "Saving %d imported templates for restaurant_id=%s (existing=%d)",
            len(rows),
            restaurant_id,
            len(existing_templates),
        )
        merged = existing_templates + rows
        return self.shift_template_service.upsert_templates(restaurant_id, merged)


template_import_service = TemplateImportService()
