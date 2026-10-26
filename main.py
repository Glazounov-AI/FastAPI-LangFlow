import os
import time
import logging
from uuid import uuid4
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


load_dotenv()

logger = logging.getLogger(__name__)

LANGFLOW_URL = (os.getenv("LANGFLOW_URL") or "http://127.0.0.1:7860").rstrip("/")
LANGFLOW_FLOW_ID = os.getenv("LANGFLOW_FLOW_ID") or ""
LANGFLOW_API_KEY = os.getenv("LANGFLOW_API_KEY") or ""

LANGFLOW_INPUT_TYPE = os.getenv("LANGFLOW_INPUT_TYPE") or "chat"
LANGFLOW_OUTPUT_TYPE = os.getenv("LANGFLOW_OUTPUT_TYPE") or "chat"

# CORS config (для Lovable/браузера)
LOVEABLE_ORIGIN = os.getenv("LOVEABLE_ORIGIN") or ""  # например: https://happy-multiply-box.lovable.app
CORS_ALLOW_ALL = (os.getenv("CORS_ALLOW_ALL") or "").lower() in ("1", "true", "yes")


# Check required env vars
missing: List[str] = []
for k, v in [
    ("LANGFLOW_URL", LANGFLOW_URL),
    ("LANGFLOW_FLOW_ID", LANGFLOW_FLOW_ID),
    ("LANGFLOW_API_KEY", LANGFLOW_API_KEY),
]:
    if not v:
        missing.append(k)

if missing:
    raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

# Создаем экземпляр FastAPI с нашим названием
app = FastAPI(title="Langflow FastAPI Proxy")

limiter = Limiter(
    key_func=lambda request: request.client.host if request.client else "unknown"
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: __import__(
        "fastapi"
    ).responses.JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Try again later."},
    ),
)
app.add_middleware(SlowAPIMiddleware)

allowed_origins = ["*"] if CORS_ALLOW_ALL else (
    [LOVEABLE_ORIGIN] if LOVEABLE_ORIGIN else []
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# trust_env=False is IMPORTANT: ignores HTTP(S)_PROXY which can break local calls
client = httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=10.0,
        read=60.0,
        write=10.0,
        pool=10.0,
    ),
    trust_env=False,
)

# Pydantic models for request and response
class MultiplyRequest(BaseModel):
    numbers: List[float] = Field(min_length=2)
    session_id: Optional[str] = None


def _extract_text_from_langflow(resp_json: Dict[str, Any]) -> Optional[str]:
    try:
        return resp_json["outputs"][0]["outputs"][0]["results"]["message"]["text"]
    except (KeyError, IndexError, TypeError):
        return None


def _make_auth_headers() -> List[Dict[str, str]]:
    # Langflow иногда ожидает один из двух вариантов авторизации
    return [
        {"Authorization": f"Bearer {LANGFLOW_API_KEY}"},
        {"x-api-key": LANGFLOW_API_KEY},
    ]


async def _run_langflow(input_value: str, session_id: str) -> Tuple[Dict[str, Any], str]:
    url = f"{LANGFLOW_URL}/api/v1/run/{LANGFLOW_FLOW_ID}"

    payload: Dict[str, Any] = {
        "input_value": input_value,
        "input_type": LANGFLOW_INPUT_TYPE,
        "output_type": LANGFLOW_OUTPUT_TYPE,
        "session_id": session_id,
        "tweaks": None,
    }

    for auth in _make_auth_headers():
        headers = {
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
            **auth,
        }

        try:
            r = await client.post(url, json=payload, headers=headers)

            if r.status_code in (401, 403):
                logger.warning(
                    "Langflow authentication rejected: HTTP %s",
                    r.status_code,
                )
                continue

            r.raise_for_status()

            try:
                response_data = r.json()
            except ValueError:
                logger.error("Langflow returned invalid JSON")
                raise HTTPException(
                    status_code=502,
                    detail="Invalid Langflow response",
                )

            return response_data, (
                "bearer" if "Authorization" in auth else "x-api-key"
            )

        except httpx.TimeoutException:
            logger.warning("Langflow request timed out")
            raise HTTPException(
                status_code=504,
                detail="Langflow response timeout",
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "Langflow returned HTTP %s",
                e.response.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail="Langflow processing error",
            )

        except httpx.RequestError as e:
            logger.error(
                "Langflow connection failed: %s",
                type(e).__name__,
            )
            raise HTTPException(
                status_code=502,
                detail="Langflow service unavailable",
            )

    logger.error("Langflow authentication failed for all configured methods")
    raise HTTPException(
        status_code=502,
        detail="Upstream authentication failed",
    )


@app.get("/")
async def root() -> Dict[str, str]:
    return {"status": "up"}

@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/multiply")
@limiter.limit("5/minute")
async def multiply(
    request: Request,
    req: MultiplyRequest,
) -> Dict[str, Any]:
    start_time = time.perf_counter()


    logger.warning(
        "Rate limit diagnostic: client_host=%s",
        request.client.host if request.client else "unknown",
    )


    input_value = " * ".join(str(x) for x in req.numbers)

    resp_json, auth_used = await _run_langflow(
        input_value=input_value,
        session_id=req.session_id or str(uuid4()),
    )

    processing_time_ms = round(
        (time.perf_counter() - start_time) * 1000, 2
    )

    return {
        "input": input_value,
        "result_text": _extract_text_from_langflow(resp_json),
        "processing_time_ms": processing_time_ms,
    }
