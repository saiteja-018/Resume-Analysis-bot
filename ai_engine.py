"""
AI Engine for CareerMatch AI bot.
Handles communication with Groq or OpenAI-compatible APIs.
"""

import logging
import asyncio
from config import AI_PROVIDER, AI_API_KEY, AI_BASE_URL, AI_MODEL, AI_TIMEOUT, AI_MAX_RETRIES
from utils import extract_json_from_text

logger = logging.getLogger(__name__)

# Initialize appropriate client
if AI_PROVIDER == "groq":
    from groq import AsyncGroq
    _client = AsyncGroq(api_key=AI_API_KEY, timeout=AI_TIMEOUT)
    logger.info(f"Initialized AsyncGroq client with model {AI_MODEL}")
else:
    from openai import AsyncOpenAI
    _client = AsyncOpenAI(base_url=AI_BASE_URL, api_key=AI_API_KEY, timeout=AI_TIMEOUT)
    logger.info(f"Initialized AsyncOpenAI client ({AI_BASE_URL}) with model {AI_MODEL}")


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
            logger.info(f"AI API call attempt {attempt}/{AI_MAX_RETRIES} using {AI_MODEL} on {AI_PROVIDER}")

            # Request JSON output
            create_kwargs = {
                "model": AI_MODEL,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 2500,
                "response_format": {"type": "json_object"},
            }

            resp = await _client.chat.completions.create(**create_kwargs)
            full_content = resp.choices[0].message.content or ""

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
                await asyncio.sleep(1)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {
                        "role": "user",
                        "content": (
                            "IMPORTANT: Your previous response was not valid JSON. "
                            "Return ONLY a valid JSON object matching the requested schema."
                        ),
                    },
                ]

        except Exception as e:
            last_error = e
            logger.error(f"Attempt {attempt} failed (API error): {e}")
            if attempt < AI_MAX_RETRIES:
                await asyncio.sleep(2)

    raise Exception(
        f"AI analysis failed after {AI_MAX_RETRIES} attempts. Last error: {last_error}"
    )
