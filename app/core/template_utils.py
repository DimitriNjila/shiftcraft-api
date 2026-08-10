from typing import Any, Dict, List, Tuple


def dedupe_shift_templates(templates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Collapse shift templates that share (day_of_week, start_time, end_time, role)
    into a single entry, keeping the max count seen across duplicates.

    Two entries with identical day/time/role are indistinguishable in the data
    model except for count, so duplicates are treated as a redundant restatement
    of the same need (e.g. importing the same file/photo twice) rather than an
    additive one — a manager who genuinely wants more people for a slot sets
    count directly, which is what that field is for.

    Preserves first-seen order for determinism.

    Args:
        templates: List of shift template dicts (day_of_week, start_time,
                   end_time, role, count)

    Returns:
        Deduplicated list of shift template dicts
    """
    merged: Dict[Tuple[Any, Any, Any, Any], Dict[str, Any]] = {}
    order: List[Tuple[Any, Any, Any, Any]] = []

    for template in templates:
        key = (
            template["day_of_week"],
            template["start_time"],
            template["end_time"],
            template["role"],
        )
        if key not in merged:
            merged[key] = dict(template)
            order.append(key)
        else:
            merged[key]["count"] = max(
                merged[key].get("count", 1), template.get("count", 1)
            )

    return [merged[key] for key in order]
