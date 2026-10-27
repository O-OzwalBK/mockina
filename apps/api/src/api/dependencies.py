"""Dependencies shared by API routers and replaceable in tests."""

from typing import cast

from fastapi import Request
from llm_gateway import LLM
from session_store import SessionStore
from skill_graph import SkillCatalog, SkillStore

from api.settings import ApiSettings


def get_llm(request: Request) -> LLM:
    """Return the app-owned language model so tests can replace the dependency."""
    return cast(LLM, request.app.state.llm)


def get_skill_catalog(request: Request) -> SkillCatalog:
    """Return the app-owned skill catalog so tests can replace catalog storage."""
    store = cast(SkillStore, request.app.state.skill_store)
    return store.catalog


def get_store(request: Request) -> SessionStore:
    """Return the app-owned session store so tests can replace the dependency."""
    return cast(SessionStore, request.app.state.store)


def get_api_settings(request: Request) -> ApiSettings:
    """Return the settings the app was built with, so tests can replace the dependency."""
    return cast(ApiSettings, request.app.state.api_settings)
