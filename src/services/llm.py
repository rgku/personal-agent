from openai import OpenAI
import httpx

from ..config import settings

client = OpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
    timeout=httpx.Timeout(60.0, connect=10.0),
)


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
):
    kwargs: dict = dict(
        model=model or settings.llm_model,
        messages=messages,
    )
    if tools:
        kwargs["tools"] = tools
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message
