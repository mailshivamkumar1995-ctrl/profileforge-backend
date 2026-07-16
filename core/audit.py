from core.models import AuditAction


def resolve_action(http_method: str, status_code: int) -> str:
    if status_code >= 400:
        return AuditAction.READ  # failed mutations don't count as writes
    method_map = {
        "POST": AuditAction.CREATE,
        "PUT": AuditAction.UPDATE,
        "PATCH": AuditAction.UPDATE,
        "DELETE": AuditAction.DELETE,
        "GET": AuditAction.READ,
    }
    return method_map.get(http_method.upper(), AuditAction.READ)
