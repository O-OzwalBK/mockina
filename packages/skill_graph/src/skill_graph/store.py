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
class CatalogSharing(Protocol):
    """Choose which catalog partitions an owner reads and where new entries are written.

    A partition is a string key; `None` is the shared seed partition that every owner
    reads. The default `PerUserSharing` keeps learned labels in the owner's own
    partition. A future policy can implement this protocol to share by team, domain,
    preparation, or a promotion threshold without changing extraction.
    """

    def visible_partitions(self, owner_id: str) -> tuple[str | None, ...]:
        """Return the partitions an owner may read, in increasing override order."""
        ...

    def write_partition(self, owner_id: str) -> str | None:
        """Return the partition in which this owner's newly learned labels are stored."""
        ...


class PerUserSharing:
    """Share the seed partition and keep every owner's learned labels private."""

    def visible_partitions(self, owner_id: str) -> tuple[str | None, ...]:
        """Read the shared seeds, then the owner's own partition."""
        return (None, owner_id)

    def write_partition(self, owner_id: str) -> str:
        """Write new labels into the owner's private partition."""
        return owner_id


@runtime_checkable
class SkillCatalog(Protocol):
    """An asynchronous store of first-seen skill labels for prompt reuse."""

    async def all_entries(self, owner_id: str) -> tuple[SkillCatalogEntry, ...]:
        """Return every entry this owner may see, in stable creation-time and ID order."""
        ...

    async def record(self, graph: SkillGraph, owner_id: str) -> None:
        """Record first sightings from this owner without replacing existing labels."""
        ...


class InMemorySkillCatalog:
    """An in-memory catalog with shared seeds and owner-scoped learned labels."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        seed_entries: tuple[SkillCatalogEntry, ...] = SEED_CATALOG,
        sharing: CatalogSharing | None = None,
    ) -> None:
        self._clock = clock
        self._sharing = sharing if sharing is not None else PerUserSharing()
        self._partitions: dict[str | None, dict[str, SkillCatalogEntry]] = {
            None: {entry.id: entry for entry in seed_entries}
        }

    async def all_entries(self, owner_id: str) -> tuple[SkillCatalogEntry, ...]:
        """Return the union of this owner's visible partitions, sorted deterministically."""
        visible: dict[str, SkillCatalogEntry] = {}
        for partition in self._sharing.visible_partitions(owner_id):
            visible.update(self._partitions.get(partition, {}))
        return tuple(sorted(visible.values(), key=lambda entry: (entry.created_at, entry.id)))

    async def record(self, graph: SkillGraph, owner_id: str) -> None:
        """Record each new ID once in the owner's partition, never replacing a seed."""
        partition = self._sharing.write_partition(owner_id)
        bucket = self._partitions.setdefault(partition, {})
        shared = self._partitions.get(None, {})
        nodes_by_id = {node.id: node for node in graph.nodes}
        timestamp = self._clock().astimezone(UTC)
        for node in graph.nodes:
            root = node
            while root.parent_id is not None:
                root = nodes_by_id[root.parent_id]
            if node.id not in bucket and node.id not in shared:
                bucket[node.id] = SkillCatalogEntry(
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
    """A v1 store whose seeded and learned catalog entries last until restart."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        sharing: CatalogSharing | None = None,
    ) -> None:
        super().__init__(catalog=InMemorySkillCatalog(clock=clock, sharing=sharing))
