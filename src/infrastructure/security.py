import os
from fastapi import Request, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

INTERNAL_TOKEN_NAME = "X-Internal-Service-Token"
api_key_header = APIKeyHeader(name=INTERNAL_TOKEN_NAME, auto_error=False)

EXPECTED_TOKEN = os.getenv("JWT_SECRET")

if not EXPECTED_TOKEN:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "The service will not start without a configured internal token."
    )


async def verify_internal_service_token(request: Request, token: str = Security(api_key_header)):
    """
    Strict security middleware verifying that service-to-service communication
    is authenticated using the token configured in the environment.
    """
    if not token or token != EXPECTED_TOKEN:
        raise HTTPException(
            status_code=403,
            detail=f"Security Refused: Missing or invalid {INTERNAL_TOKEN_NAME}. Unauthorized internal access."
        )
    return token
