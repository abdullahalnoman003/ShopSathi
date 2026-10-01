"""User roles. See the access matrix in docs/CONVENTIONS.md."""

OWNER = "owner"
MODERATOR = "moderator"
PLATFORM_ADMIN = "platform_admin"

# Roles that belong to a shop. The platform admin is never a shop user.
SHOP_ROLES = (OWNER, MODERATOR)
