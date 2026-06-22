"""
Provider-agnostic LLM evaluation interface.

Picks OpenAI or Gemini based on which API key is configured (OPENAI_API_KEY
takes priority if both are set). Built behind a single call_llm_evaluation()
function so Anthropic (langchain-anthropic) can be added the same way later
without touching the orchestrator.

The evaluation prompt forces structured JSON output and explicitly instructs
the model to prefer NEEDS_REVIEW over guessing on ambiguous transcripts --
this is what makes the human-in-the-loop status a real, reachable outcome
rather than a schema value nothing ever triggers.
"""
import json
import logging
from typing import TypedDict

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EvaluationResult(TypedDict):
    status: str  # "QUALIFIED" | "NOT_INTERESTED" | "NEEDS_REVIEW"
    reasoning: str
    summary: str


SYSTEM_PROMPT = """You are a lead-qualification evaluator for a voice AI sales platform.

You will be given:
1. The company's qualification criteria.
2. A transcript (and possibly a call summary) of a phone conversation between
   an AI voice agent and a prospective lead.

Your job is to classify the outcome of the call into exactly one of:
- "QUALIFIED": the lead clearly meets the company's stated criteria and showed genuine interest.
- "NOT_INTERESTED": the lead explicitly declined, hung up early, or clearly does not match the criteria.
- "NEEDS_REVIEW": the transcript is ambiguous, incomplete, cut off, or you are not confident
  in either of the above. DO NOT GUESS. If in doubt, choose NEEDS_REVIEW.

Respond with ONLY a JSON object, no markdown fences, no preamble, in exactly this shape:
{"status": "...", "reasoning": "...", "summary": "..."}

"reasoning" should be 1-3 concise sentences explaining the classification.
"summary" should be a neutral 1-2 sentence summary of what was discussed.
"""


def _build_user_prompt(company_criteria: str, transcript: str, vapi_summary: str | None) -> str:
    parts = [f"COMPANY QUALIFICATION CRITERIA:\n{company_criteria}\n"]
    if vapi_summary:
        parts.append(f"CALL SUMMARY (provided by voice platform):\n{vapi_summary}\n")
    parts.append(f"FULL TRANSCRIPT:\n{transcript}")
    return "\n".join(parts)


def _parse_llm_json(raw_text: str) -> EvaluationResult:
    cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(cleaned)

    status = data.get("status", "NEEDS_REVIEW")
    if status not in ("QUALIFIED", "NOT_INTERESTED", "NEEDS_REVIEW"):
        status = "NEEDS_REVIEW"

    return EvaluationResult(
        status=status,
        reasoning=data.get("reasoning", ""),
        summary=data.get("summary", ""),
    )


def _evaluate_with_openai(user_prompt: str) -> EvaluationResult:
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw_text = response.choices[0].message.content
    return _parse_llm_json(raw_text)


def _evaluate_with_gemini(user_prompt: str) -> EvaluationResult:
    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"},
    )
    response = model.generate_content(user_prompt)
    return _parse_llm_json(response.text)


def get_mock_transcript_and_eval(customer_name: str, customer_phone: str = None) -> tuple[str, str, dict]:
    """
    Generates a realistic transcript, summary, and evaluation classification
    for demo purposes when SIMULATION_MODE is active.
    """
    phone = customer_phone or ""
    is_elite = "55502" in phone or "Elite" in customer_name or "Sara" in customer_name or "Marcus" in customer_name or "Aiko" in customer_name
    
    if phone.endswith("1") or (not phone and "Rohan" in customer_name) or (not phone and "Sara" in customer_name):
        if is_elite:
            transcript = (
                f"Agent: Hi {customer_name}, I'm calling from Elite Rentals. Are you looking to rent an apartment?\n"
                f"User: Yes, I'm looking for a 12-month lease with a budget of $3,500/month."
            )
            summary = "Lead is interested in a 12-month lease."
            evaluation = {
                "status": "QUALIFIED",
                "reasoning": "Lead wants a 12-month lease, matching the company's requirement.",
                "summary": summary
            }
        else:
            transcript = (
                f"Agent: Hi {customer_name}, I'm calling from Apex Properties. Are you looking to buy a house?\n"
                f"User: Yes, I am. My budget is $500,000, and I'd like to buy in Seattle within 2 months."
            )
            summary = "Lead is interested in buying a house in Seattle with a budget of $500k."
            evaluation = {
                "status": "QUALIFIED",
                "reasoning": "Lead confirmed budget of $500k and timeline of 2 months, which matches the criteria of >=$400k.",
                "summary": summary
            }
    elif phone.endswith("2") or (not phone and "Priya" in customer_name) or (not phone and "Marcus" in customer_name):
        if is_elite:
            transcript = (
                f"Agent: Hi {customer_name}, I'm calling from Elite Rentals. Are you looking to rent an apartment?\n"
                f"User: Only for a short term, like 2 or 3 months maximum."
            )
            summary = "Lead wants a short term lease."
            evaluation = {
                "status": "NOT_INTERESTED",
                "reasoning": "Lead wants a 2-3 month lease, which is below the 12-month requirement.",
                "summary": summary
            }
        else:
            transcript = (
                f"Agent: Hi {customer_name}, I'm calling from Apex Properties. Are you looking to buy a house?\n"
                f"User: No, I'm not interested in buying right now. Thanks."
            )
            summary = "Lead is not interested in buying."
            evaluation = {
                "status": "NOT_INTERESTED",
                "reasoning": "Lead explicitly stated she is not interested in buying.",
                "summary": summary
            }
    else:
        transcript = (
            "Agent: Hi, are you interested?\n"
            "User: Maybe, but I have to go now. Call me back."
        )
        summary = "Incomplete call."
        evaluation = {
            "status": "NEEDS_REVIEW",
            "reasoning": "Call was cut off; lead is ambiguous. Flagged for review.",
            "summary": summary
        }
    return transcript, summary, evaluation


def call_llm_evaluation(
    *,
    company_criteria: str,
    transcript: str,
    vapi_summary: str | None = None,
) -> EvaluationResult:
    """
    Dispatches to whichever LLM provider is configured. Raises RuntimeError
    if no provider key is set, or returns a NEEDS_REVIEW fallback if the
    provider call fails/parses incorrectly (fail-safe, never silently
    misclassify on an error).
    """
    if settings.SIMULATION_MODE:
        if "Seattle" in transcript or "500,000" in transcript:
            mock_status = "QUALIFIED"
            mock_reasoning = "Lead confirmed budget of $500k and wants to buy in Seattle within 2 months."
            mock_summary = "Interested in buying a house in Seattle with a budget of $500k."
        elif "12-month" in transcript or "3,500" in transcript:
            mock_status = "QUALIFIED"
            mock_reasoning = "Lead wants a 12-month lease at $3,500/month, matching criteria."
            mock_summary = "Interested in renting an apartment."
        elif "not interested" in transcript:
            mock_status = "NOT_INTERESTED"
            mock_reasoning = "Lead explicitly stated not interested."
            mock_summary = "Lead is not interested."
        elif "short term" in transcript:
            mock_status = "NOT_INTERESTED"
            mock_reasoning = "Lead wants a short term lease (2-3 months), which does not meet criteria."
            mock_summary = "Wants short-term lease."
        else:
            mock_status = "NEEDS_REVIEW"
            mock_reasoning = "Incomplete call; lead is ambiguous. Flagged for review."
            mock_summary = "Ambiguous or incomplete conversation."
            
        return EvaluationResult(
            status=mock_status,
            reasoning=mock_reasoning,
            summary=vapi_summary or mock_summary,
        )

    user_prompt = _build_user_prompt(company_criteria, transcript, vapi_summary)

    try:
        if settings.OPENAI_API_KEY:
            return _evaluate_with_openai(user_prompt)
        if settings.GEMINI_API_KEY:
            return _evaluate_with_gemini(user_prompt)
        raise RuntimeError(
            "No LLM API key configured. Set OPENAI_API_KEY or GEMINI_API_KEY."
        )
    except Exception as exc:  # noqa: BLE001 - intentional broad catch, fail safe
        logger.error("LLM evaluation failed, falling back to NEEDS_REVIEW: %s", exc)
        return EvaluationResult(
            status="NEEDS_REVIEW",
            reasoning=f"Automatic evaluation failed ({exc}); flagged for manual review.",
            summary=vapi_summary or "Summary unavailable due to evaluation error.",
        )
