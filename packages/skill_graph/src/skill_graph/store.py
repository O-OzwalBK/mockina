"""In-memory storage for stable global skill labels and root relationships."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from contracts import SkillGraph, UtcDatetime, skill_id, utc_now

SEED_LABELS = (
    "JavaScript",
    "TypeScript",
    "Python",
    "SQL",
    "React",
    "Vue",
    "Node.js",
    "Docker",
    "Kubernetes",
    "PostgreSQL",
    "MongoDB",
    "Git",
)
SEED_CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class SkillCatalogEntry:
    """A first-seen skill identity, scoped to its root and without preparation metadata."""

    id: str
    """The stable UUIDv5 identity for this root and node label."""

    root_label: str
    """The root category used to scope the stable identity."""

    node_label: str
    """The first label recorded for this identity, kept for prompt reuse."""

    created_at: UtcDatetime
    """When the catalog first saw this identity; later sightings do not change it."""


SEED_CATALOG = tuple(
    SkillCatalogEntry(
        id=skill_id(label, label),
        root_label=label,
        node_label=label,
        created_at=SEED_CREATED_AT,
    )
    for label in SEED_LABELS
)


@runtime_checkable
class SkillCatalog(Protocol):
    """An asynchronous store of first-seen skill labels for prompt reuse."""

    async def all_entries(self) -> tuple[SkillCatalogEntry, ...]:
        """Return every catalog entry in stable creation-time and ID order."""
        ...

    async def record(self, graph: SkillGraph) -> None:
        """Record first sightings in a graph without replacing existing labels."""
        ...


class InMemorySkillCatalog:
    """An in-memory catalog that keeps the first label and timestamp for each ID."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        seed_entries: tuple[SkillCatalogEntry, ...] = SEED_CATALOG,
    ) -> None:
        self._clock = clock
        self._entries = {entry.id: entry for entry in seed_entries}

    async def all_entries(self) -> tuple[SkillCatalogEntry, ...]:
        """Return entries sorted by first-seen time and ID for deterministic consumers."""
        return tuple(sorted(self._entries.values(), key=lambda entry: (entry.created_at, entry.id)))

    async def record(self, graph: SkillGraph) -> None:
        """Record each new ID once, keeping catalog labels separate from graph metadata."""
        nodes_by_id = {node.id: node for node in graph.nodes}
        timestamp = self._clock().astimezone(UTC)
        for node in graph.nodes:
            root = node
            while root.parent_id is not None:
                root = nodes_by_id[root.parent_id]
            if node.id not in self._entries:
                self._entries[node.id] = SkillCatalogEntry(
                    id=node.id,
                    root_label=root.label,
                    node_label=node.label,
                    created_at=timestamp,
                )


@dataclass(frozen=True)
class SkillStore:
    """A container for the catalog and future preparation-specific persistence."""

    catalog: SkillCatalog
    """Catalog storage used by extraction and future persistence adapters."""


class InMemorySkillStore(SkillStore):
    """A v1 store whose seeded and first-seen catalog entries last until restart."""

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        object.__setattr__(self, "catalog", InMemorySkillCatalog(clock=clock))
