"""Multi-provider model router — WP-01 / freeze gate G-MODEL-ROUTER.

Routes each agent *role* to an ordered provider chain and falls back to OpenAI on
any error (timeout / 429 / quota / connection). AI/ML API and Featherless are both
OpenAI-compatible, so every provider is reached through the OpenAI SDK with a
swapped ``base_url`` — there is exactly one client type and one call site.

Public surface (the frozen contract):
  - ``get_client(role_or_provider)`` → an ``OpenAI`` client for a role's PRIMARY
    provider, or for a named provider. Lets callers/tests introspect the binding.
  - ``chat_completion(role, messages, **params)`` → tries the role's chain in order,
    falls back on failure, and returns a structured result:
        {content, provider, model, usage, estimated_cost, attempts}
  - ``route(role)`` → the ordered ``[(provider, model), ...]`` chain for a role.

Roles: ``intake`` (Featherless), ``escalation``/``cfo`` (AI/ML), ``compliance`` /
``format`` (Featherless). Every chain terminates in ``openai`` as the fallback.
"""

import os
from dataclasses import dataclass

from openai import OpenAI


# --- Provider registry -----------------------------------------------------

@dataclass(frozen=True)
class _Provider:
    name: str
    base_url_env: str        # env var holding the base URL ("" → OpenAI default endpoint)
    base_url_default: str
    api_key_env: str
    input_cost: float        # USD per 1M input tokens (best-effort; OpenAI is the known one)
    output_cost: float       # USD per 1M output tokens


PROVIDERS = {
    "aiml": _Provider("aiml", "AIML_BASE_URL", "https://api.aimlapi.com/v1", "AIML_API_KEY", 0.0, 0.0),
    "featherless": _Provider("featherless", "FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1", "FEATHERLESS_API_KEY", 0.0, 0.0),
    "openai": _Provider("openai", "", "", "OPENAI_API_KEY", 0.150, 0.600),
}

# role → ordered chain of (provider, model_env, default_model). OpenAI is always the
# terminal fallback so any role degrades gracefully when a partner provider is down.
ROLE_ROUTES = {
    "intake":     [("featherless", "FEATHERLESS_INTAKE_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
                   ("openai", "OPENAI_MODEL", "gpt-4o-mini")],
    "escalation": [("aiml", "AIML_ESCALATION_MODEL", "gpt-4o"),
                   ("openai", "OPENAI_MODEL", "gpt-4o-mini")],
    "cfo":        [("aiml", "AIML_CFO_MODEL", "gpt-4o"),
                   ("openai", "OPENAI_MODEL", "gpt-4o-mini")],
    "compliance": [("featherless", "FEATHERLESS_COMPLIANCE_MODEL", "mistralai/Mistral-Small-24B-Instruct-2501"),
                   ("openai", "OPENAI_MODEL", "gpt-4o-mini")],
    "format":     [("featherless", "FEATHERLESS_COMPLIANCE_MODEL", "mistralai/Mistral-Small-24B-Instruct-2501"),
                   ("openai", "OPENAI_MODEL", "gpt-4o-mini")],
}
DEFAULT_ROLE = "intake"

# Cumulative best-effort spend this process; gated by MODEL_ROUTER_SPEND_CEILING_USD.
_spent_usd = 0.0


def _cfg(key, default=""):
    """Read a setting from the Flask app config if available, else the environment."""
    try:
        from flask import current_app
        if current_app:
            return current_app.config.get(key, os.getenv(key, default))
    except Exception:
        pass
    return os.getenv(key, default)


def route(role):
    """Return the ordered ``[(provider, model), ...]`` chain for a role."""
    chain = ROLE_ROUTES.get(role, ROLE_ROUTES[DEFAULT_ROLE])
    return [(p, _cfg(model_env, default)) for (p, model_env, default) in chain]


def get_client(role_or_provider):
    """Return an OpenAI-compatible client for a role's primary provider or a named provider."""
    name = role_or_provider
    if role_or_provider in ROLE_ROUTES:
        name = ROLE_ROUTES[role_or_provider][0][0]
    if name not in PROVIDERS:
        raise ValueError(f"unknown provider/role: {role_or_provider!r}")
    prov = PROVIDERS[name]
    kwargs = {"api_key": _cfg(prov.api_key_env, "")}
    base_url = _cfg(prov.base_url_env, prov.base_url_default) if prov.base_url_env else ""
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _ceiling():
    try:
        return float(_cfg("MODEL_ROUTER_SPEND_CEILING_USD", "0") or 0)
    except (TypeError, ValueError):
        return 0.0


def _estimate_cost(provider_name, usage):
    prov = PROVIDERS[provider_name]
    pt = getattr(usage, "prompt_tokens", 0) or 0
    ct = getattr(usage, "completion_tokens", 0) or 0
    return pt * prov.input_cost / 1_000_000 + ct * prov.output_cost / 1_000_000


def chat_completion(role, messages, **params):
    """Run a chat completion for ``role``, falling back down the chain on any error.

    Returns ``{content, provider, model, usage, estimated_cost, attempts}``.
    Raises ``RuntimeError`` only if every provider in the chain fails.
    """
    global _spent_usd
    ceiling = _ceiling()
    errors = []
    chain = ROLE_ROUTES.get(role, ROLE_ROUTES[DEFAULT_ROLE])

    for provider_name, model_env, default_model in chain:
        # Spend guard: once over the ceiling, skip paid partner providers and let the
        # chain drop to OpenAI (the last entry), which we still attempt.
        if ceiling and _spent_usd >= ceiling and provider_name != "openai":
            errors.append((provider_name, "skipped: spend ceiling reached"))
            continue

        model = _cfg(model_env, default_model)
        try:
            client = get_client(provider_name)
            resp = client.chat.completions.create(model=model, messages=messages, **params)
            usage = getattr(resp, "usage", None)
            est = _estimate_cost(provider_name, usage)
            _spent_usd += est
            return {
                "content": resp.choices[0].message.content,
                "provider": provider_name,
                "model": model,
                "usage": {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                },
                "estimated_cost": est,
                "attempts": len(errors) + 1,
            }
        except Exception as e:  # timeout / 429 / quota / connection / bad response
            errors.append((provider_name, str(e)))
            continue

    raise RuntimeError(f"all providers failed for role {role!r}: {errors}")
