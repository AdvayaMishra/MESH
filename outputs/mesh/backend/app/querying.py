from fastapi import HTTPException


def ordered(query, model, field: str, direction: str, allowed: set[str]):
    """Column names come from a route-owned allowlist, never SQL text from a request."""
    if field not in allowed or direction not in {"asc", "desc"}:
        raise HTTPException(422, "Unsupported collection sort")
    column = getattr(model, field)
    return query.order_by(column.desc() if direction == "desc" else column.asc(), model.id.asc())
