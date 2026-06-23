from __future__ import annotations

import hmac

from fastapi import HTTPException, Query, status

from app.config import get_settings


async def require_token(token: str = Query(default="")) -> None:
    """Validate dashboard/API shared token.

    Replace this with OIDC/SAML before enterprise deployment. The shared-token gate keeps the
    GitHub-ready starter simple while preventing accidental open dashboards.
    """

    expected = get_settings().rep_shared_token.get_secret_value()
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
