$content = @'
import hmac
import os
from fastapi import Request, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from src.infrastructure.messaging.token_rotator import TokenRotationEngine

INTERNAL_TOKEN_NAME = "X-Internal-Service-Token"
api_key_header = APIKeyHeader(name=INTERNAL_TOKEN_NAME, auto_error=False)

_STATIC_FALLBACK = os.getenv("JWT_SECRET")
if not _STATIC_FALLBACK:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "The service will not start without a configured internal token."
    )

_rotation_engine = TokenRotationEngine()


async def verify_internal_service_token(request: Request, token: str = Security(api_key_header)):
    if not token:
        raise HTTPException(status_code=403, detail=f"Security Refused: Missing {INTERNAL_TOKEN_NAME}.")

    try:
        if _rotation_engine.validate_incoming_token(token):
            return token
    except Exception:
        pass

    if hmac.compare_digest(token, _STATIC_FALLBACK):
        return token

    raise HTTPException(
        status_code=403,
        detail=f"Security Refused: Missing or invalid {INTERNAL_TOKEN_NAME}. Unauthorized internal access."
    )
'@

$targetPath = "$PWD\src\infrastructure\security.py"
$targetDir = Split-Path $targetPath

if (!(Test-Path $targetDir)) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
}

[System.IO.File]::WriteAllText($targetPath, $content, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "security.py updated successfully"
