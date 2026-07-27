import os
from fastapi import Request, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

# Define the strict configuration metadata for internal multi-tenant routing
INTERNAL_TOKEN_NAME = "X-Internal-Service-Token"
api_key_header = APIKeyHeader(name=INTERNAL_TOKEN_NAME, auto_error=False)

async def verify_internal_service_token(request: Request, token: str = Security(api_key_header)):
    """
    Strict security middleware verifying that service-to-service communication 
    is authenticated and matches the dynamic JWT/Secret decoupled via environment variables.
    """
    expected_token = os.getenv("JWT_SECRET", "CEOPRO_AI_SECURE_TOKEN_2026_DO_NOT_HARDCODE_IN_PRODUCTION")
    
    if not token or token != expected_token:
        raise HTTPException(
            status_code=403,
            detail=f"Security Refused: Missing or invalid {INTERNAL_TOKEN_NAME}. Unauthorized internal access."
        )
    return token
