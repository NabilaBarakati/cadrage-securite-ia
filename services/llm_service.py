import os
import json
from pathlib import Path
from typing import Dict, Generator, List, Optional

import anthropic

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "La variable d'environnement ANTHROPIC_API_KEY n'est pas définie."
        )
    return anthropic.Anthropic(api_key=api_key)


def _build_system_prompt(step: dict, project_name: str, project_desc: str, previous_context: str) -> str:
    raw = step["prompt"]
    return raw.format(
        project_name=project_name,
        project_desc=project_desc,
        previous_steps_context=previous_context or "Aucun contexte précédent disponible.",
    )


def _format_previous_context(step_responses: List[Dict]) -> str:
    """Build a readable summary of previous steps to inject as context."""
    if not step_responses:
        return ""
    parts: List[str] = []
    for sr in step_responses:
        parts.append(
            f"### Étape {sr['step_number']} — résultat\n{sr['ai_response']}"
        )
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_steps() -> List[Dict]:
    """Return the ordered list of step metadata (number, title, icon…)."""
    config = _load_config()
    return [
        {
            "number": s["number"],
            "title": s["title"],
            "short_title": s["short_title"],
            "icon": s["icon"],
        }
        for s in config["steps"]
    ]


def get_step(step_number: int) -> dict:
    config = _load_config()
    for s in config["steps"]:
        if s["number"] == step_number:
            return s
    raise ValueError(f"Étape {step_number} introuvable dans config.json")


def stream_step_response(
    step_number: int,
    project_name: str,
    project_desc: str,
    previous_step_responses: List[Dict],
    chat_history: Optional[List[Dict]] = None,
) -> Generator[str, None, None]:
    """
    Stream the AI response for a given step.

    Parameters
    ----------
    step_number : int
        The step to execute (1-10).
    project_name : str
        Name of the project being analysed.
    project_desc : str
        Description of the project.
    previous_step_responses : list[dict]
        Records from step_responses table for earlier steps (step_number < current).
        Each dict must contain at least {'step_number': int, 'ai_response': str}.
    chat_history : list[dict] | None
        Optional existing chat history for this step, as a list of
        {'role': 'user'|'assistant', 'content': str}.
        When provided, the initial AI analysis is assumed already generated and
        only the follow-up exchange is sent.

    Yields
    ------
    str
        Text chunks as they stream from the API.
    """
    config = _load_config()
    app_cfg = config["app"]
    step = get_step(step_number)

    previous_context = _format_previous_context(previous_step_responses)
    system_prompt = _build_system_prompt(step, project_name, project_desc, previous_context)

    if chat_history:
        messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in chat_history
        ]
    else:
        messages = [
            {
                "role": "user",
                "content": (
                    f"Lance l'analyse de l'étape {step_number} : **{step['title']}**.\n"
                    "Produis une analyse complète et structurée selon tes instructions."
                ),
            }
        ]

    client = _get_client()

    with client.messages.stream(
        model=app_cfg["model"],
        max_tokens=app_cfg["max_tokens"],
        system=system_prompt,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def stream_chat_followup(
    step_number: int,
    project_name: str,
    project_desc: str,
    previous_step_responses: List[Dict],
    chat_history: List[Dict],
    user_message: str,
) -> Generator[str, None, None]:
    """
    Stream a follow-up response to a user challenge/question on a step.

    The full chat_history (including all prior exchanges) is passed so the model
    keeps context. The user_message is appended as the latest user turn.

    Yields
    ------
    str
        Text chunks as they stream from the API.
    """
    config = _load_config()
    app_cfg = config["app"]
    step = get_step(step_number)

    previous_context = _format_previous_context(previous_step_responses)
    system_prompt = _build_system_prompt(step, project_name, project_desc, previous_context)

    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in chat_history
    ]
    messages.append({"role": "user", "content": user_message})

    client = _get_client()

    with client.messages.stream(
        model=app_cfg["model"],
        max_tokens=app_cfg["max_tokens"],
        system=system_prompt,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def get_all_steps_full() -> List[Dict]:
    """Return all steps including their prompt text (for admin editing)."""
    return _load_config()["steps"]


def update_step_prompt(step_number: int, new_prompt: str) -> None:
    """Persist an updated prompt for a step to config.json."""
    config = _load_config()
    for step in config["steps"]:
        if step["number"] == step_number:
            step["prompt"] = new_prompt
            break
    else:
        raise ValueError(f"Étape {step_number} introuvable dans config.json")
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def collect_stream(generator: Generator[str, None, None]) -> str:
    """Consume a streaming generator and return the full response string."""
    return "".join(generator)
