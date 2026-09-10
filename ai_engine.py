"""
AI Engine for CareerMatch AI bot.
Handles communication with the TokenRouter API using the OpenAI SDK.
"""

import logging
import asyncio
from openai import AsyncOpenAI
from config import AI_BASE_URL, TOKENROUTER_API_KEY, AI_MODEL, AI_TIMEOUT, AI_MAX_RETRIES
from utils import extract_json_from_text

logger = logging.getLogger(__name__)

# Initialize the async OpenAI client with TokenRouter base URL
_client = AsyncOpenAI(
    base_url=AI_BASE_URL,
    api_key=TOKENROUTER_API_KEY,
    timeout=AI_TIMEOUT,
)


async def analyze(system_prompt: str, user_message: str) -> dict:
    """
    Send analysis request to the AI model and return parsed JSON response.

    Args:
        system_prompt: The full CareerMatch AI system prompt.
        user_message: The structured user input (resume, JD, question, etc.).

    Returns:
        Parsed JSON dict from the AI response.

    Raises:
        ValueError: If the AI response cannot be parsed as valid JSON.
        Exception: If the API call fails after retries.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    last_error = None

    for attempt in range(1, AI_MAX_RETRIES + 1):
        try:
            logger.info(f"AI API call attempt {attempt}/{AI_MAX_RETRIES}")

            # Use streaming to collect the response
            content_parts = []
            stream = await _client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                temperature=0.3,  # Lower temperature for more consistent JSON
                extra_body={},
            )

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        content_parts.append(delta.content)

            full_content = "".join(content_parts)

            if not full_content.strip():
                raise ValueError("AI returned an empty response.")

            # Parse JSON from the response
            result = extract_json_from_text(full_content)

            if result is None:
                raise ValueError(
                    f"Could not parse JSON from AI response. "
                    f"Raw response (first 500 chars): {full_content[:500]}"
                )

            # Validate essential fields
            if "analysis_type" not in result:
                logger.warning("AI response missing 'analysis_type' field, adding default.")
                result["analysis_type"] = "unknown"

            if "status" not in result:
                result["status"] = "success"

            logger.info(
                f"AI analysis complete. Type: {result.get('analysis_type')}, "
                f"Status: {result.get('status')}"
            )
            return result

        except ValueError as e:
            last_error = e
            logger.warning(f"Attempt {attempt} failed (parse error): {e}")
            if attempt < AI_MAX_RETRIES:
                await asyncio.sleep(2)
                # On retry, add a reminder to return valid JSON
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {
                        "role": "user",
                        "content": (
                            "IMPORTANT: Your previous response was not valid JSON. "
                            "Return ONLY a valid JSON object with no markdown, "
                            "no code fences, and no text outside the JSON."
                        ),
                    },
                ]

        except Exception as e:
            last_error = e
            logger.error(f"Attempt {attempt} failed (API error): {e}")
            if attempt < AI_MAX_RETRIES:
                await asyncio.sleep(3)

    raise Exception(
        f"AI analysis failed after {AI_MAX_RETRIES} attempts. Last error: {last_error}"
    )


async def health_check() -> bool:
    """Quick health check to verify the API connection."""
    try:
        content_parts = []
        stream = await _client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "user", "content": 'Respond with exactly: {"status":"ok"}'},
            ],
            stream=True,
            extra_body={},
        )
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    content_parts.append(delta.content)
        return bool(content_parts)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False
