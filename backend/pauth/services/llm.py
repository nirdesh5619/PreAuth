"""OpenAI chat client used by specialist nodes when `settings.use_llm` is true."""

from langchain_openai import ChatOpenAI

from pauth.config import settings


def get_llm() -> ChatOpenAI:
    """Return a low-temperature ChatOpenAI bound to `LLM_MODEL` and `.env` key."""
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key.strip(),
        temperature=0,
        max_tokens=4096,
    )
