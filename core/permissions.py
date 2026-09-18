"""RBAC — Role Based Access Control.

Roles: OWNER > ADMIN > MODERATOR > USER
Permissions are checked per action; OWNER has all.
"""
from __future__ import annotations
import logging
from typing import Optional, Set, Dict, List

logger = logging.getLogger(__name__)

ROLES = ("owner", "admin", "moderator", "user")

# Default permission sets per role
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "owner": {
        "stream.create", "stream.stop", "stream.restart", "stream.view",
        "files.upload", "files.delete", "files.view",
        "users.manage", "users.ban", "users.view",
        "system.monitor", "system.maintenance", "system.backup",
        "admin.panel", "api.access", "iptv.manage", "plugins.manage",
    },
    "admin": {
        "stream.create", "stream.stop", "stream.restart", "stream.view",
        "files.upload", "files.delete", "files.view",
        "users.manage", "users.ban", "users.view",
        "system.monitor", "system.maintenance",
        "admin.panel", "api.access", "iptv.manage",
    },
    "moderator": {
        "stream.create", "stream.stop", "stream.restart", "stream.view",
        "files.upload", "files.view",
        "users.view",
        "system.monitor",
        "iptv.manage",
    },
    "user": {
        "stream.create", "stream.stop", "stream.restart", "stream.view",
        "files.upload", "files.delete", "files.view",
    },
}

# In-memory overrides: user_id -> set of extra permissions
_extra_perms: Dict[int, Set[str]] = {}
_denied_perms: Dict[int, Set[str]] = {}


def normalize_role(role: Optional[str]) -> str:
    r = (role or "user").strip().lower()
    if r in ("owner", "admin", "moderator", "user"):
        return r
    if r in ("administrator",):
        return "admin"
    return "user"


def permissions_for_role(role: str) -> Set[str]:
    return set(ROLE_PERMISSIONS.get(normalize_role(role), ROLE_PERMISSIONS["user"]))


def grant_permission(user_id: int, perm: str):
    _extra_perms.setdefault(user_id, set()).add(perm)
    _denied_perms.get(user_id, set()).discard(perm)


def revoke_permission(user_id: int, perm: str):
    _denied_perms.setdefault(user_id, set()).add(perm)
    _extra_perms.get(user_id, set()).discard(perm)


def clear_overrides(user_id: int):
    _extra_perms.pop(user_id, None)
    _denied_perms.pop(user_id, None)


def effective_permissions(user_id: int, role: str) -> Set[str]:
    perms = permissions_for_role(role)
    perms |= _extra_perms.get(user_id, set())
    perms -= _denied_perms.get(user_id, set())
    return perms


def has_permission(user_id: int, role: str, permission: str) -> bool:
    role = normalize_role(role)
    if role == "owner":
        return True
    return permission in effective_permissions(user_id, role)


async def check_user_permission(user_id: int, permission: str, admin_id: int = 0) -> bool:
    """Load role from DB and check permission. OWNER = ADMIN_ID from config."""
    try:
        from database import db
        if admin_id and user_id == admin_id:
            return True
        user = await db.get_user(user_id)
        role = (user or {}).get("role") or "user"
        if user_id == admin_id:
            role = "owner"
        # Persistent per-user override wins over the role default.
        overrides = await db.get_user_permissions(user_id)
        if permission in overrides:
            return bool(overrides[permission])
        return has_permission(user_id, role, permission)
    except Exception as e:
        logger.warning("permission check failed: %s", e)
        return user_id == admin_id


def require_perm(permission: str):
    """Decorator for handlers — expects update with effective_user."""
    def decorator(fn):
        async def wrapper(update, context, *args, **kwargs):
            from config import ADMIN_ID
            user = update.effective_user
            if not user:
                return
            ok = await check_user_permission(user.id, permission, ADMIN_ID)
            if not ok:
                q = getattr(update, "callback_query", None)
                if q:
                    await q.answer("⛔ ليس لديك صلاحية: " + permission, show_alert=True)
                elif update.effective_message:
                    await update.effective_message.reply_text(f"⛔ ليس لديك صلاحية: `{permission}`", parse_mode="Markdown")
                return
            return await fn(update, context, *args, **kwargs)
        return wrapper
    return decorator
