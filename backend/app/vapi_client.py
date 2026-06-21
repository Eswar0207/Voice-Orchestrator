"""
Wrapper around the Vapi.ai REST API for triggering outbound calls.

Builds a dynamic system prompt per-call from the Company's prompt_instructions
so a single Vapi Assistant can serve every tenant (Dynamic Prompting bonus),
and stamps internal customer_id/company_id into call metadata so the webhook
handler can link the eventual end-of-call-report back to the right row
without a secondary lookup by phone number.
"""
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VapiCallError(Exception):
    """Raised when Vapi rejects or fails to process an outbound call request."""


def build_system_prompt(company_prompt_instructions: str, customer_name: str, company_name: str) -> str:
    return (
        f"{company_prompt_instructions}\n\n"
        f"You are calling {customer_name} on behalf of {company_name}. "
        f"Greet them by name, explain why you're calling in one sentence, then "
        f"ask the qualifying questions naturally as a conversation, not a script. "
        f"If they are not interested, thank them and end the call politely."
    )


def trigger_outbound_call(
    *,
    customer_id: str,
    company_id: str,
    customer_name: str,
    customer_phone: str,
    company_name: str,
    company_prompt_instructions: str,
) -> str:
    """
    Triggers a Vapi outbound call. Returns the Vapi call ID on success.
    Raises VapiCallError on any failure so the caller can mark the lead FAILED
    instead of leaving it stuck in CALL_INITIATED.
    """
    if not settings.VAPI_PRIVATE_KEY:
        raise VapiCallError("VAPI_PRIVATE_KEY is not configured")

    system_prompt = build_system_prompt(company_prompt_instructions, customer_name, company_name)

    payload = {
        "assistantId": settings.VAPI_ASSISTANT_ID,
        "phoneNumberId": settings.VAPI_PHONE_NUMBER_ID,
        "customer": {"number": customer_phone},
        "assistantOverrides": {
            "variableValues": {
                "customerName": customer_name,
                "companyName": company_name,
            },
            "model": {
                "messages": [
                    {"role": "system", "content": system_prompt},
                ]
            },
        },
        "metadata": {
            "customer_id": customer_id,
            "company_id": company_id,
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.VAPI_PRIVATE_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(f"{settings.VAPI_API_BASE}/call", json=payload, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("Vapi call failed for customer %s: %s", customer_id, exc.response.text)
        raise VapiCallError(f"Vapi API returned {exc.response.status_code}: {exc.response.text}") from exc
    except httpx.RequestError as exc:
        logger.error("Vapi call request error for customer %s: %s", customer_id, exc)
        raise VapiCallError(f"Vapi request failed: {exc}") from exc

    data = response.json()
    call_id = data.get("id")
    if not call_id:
        raise VapiCallError(f"Vapi response missing call id: {data}")

    return call_id
