"""Factory helpers for ViMax chat model configuration."""

from __future__ import annotations

import importlib
from typing import Any, Dict

from langchain.chat_models import init_chat_model

from utils.provider_presets import resolve_chat_model_config


def build_chat_model(section: Dict[str, Any], init_chat_model_func=init_chat_model) -> Any:
    """Build a chat model from either a class path or LangChain init args."""
    if "class_path" in section:
        return _instantiate(section)

    init_args = section.get("init_args", section)
    chat_model_args = resolve_chat_model_config(init_args)
    return init_chat_model_func(**chat_model_args)


def _instantiate(section: Dict[str, Any]) -> Any:
    module_path, cls_name = section["class_path"].rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name)
    init_args = section.get("init_args", {}) or {}
    return cls(**init_args)
