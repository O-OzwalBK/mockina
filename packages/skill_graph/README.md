# skill_graph

`skill_graph` extracts a technical skill hierarchy from a job title and description. The engine
can ask questions about the leaves, while parent nodes group related skills for later views. The
package owns extraction prompts and validation; shared graph models and skill IDs live in
`contracts`.

## Quick start

Pass an `LLM` and a `SkillCatalog` to the async extractor. The job description is treated as
untrusted data, and resumes are not sent to this package.

```python
from llm_gateway import LLM
from skill_graph import InMemorySkillCatalog, extract_skills


async def extract(llm: LLM):
    catalog = InMemorySkillCatalog()
    return await extract_skills(
        llm,
        catalog,
        job_title="Junior React Developer",
        job_description="Build accessible interfaces with React and TypeScript.",
    )
```

The result is a `contracts.SkillGraph` containing flat `SkillNode` values with `parent_id` links.
Each node ID is computed by `contracts.skill_id`; the model never creates IDs. Leaves carry
preparation-specific importance and expected difficulty, each from 1 to 5.

## Extraction behavior

- The model prompt prefers two levels but accepts depth three. It aims for 8–15 leaf skills; the
  validator accepts 3–30 so a vague job does not waste a repair request.
- The model returns a nested `categories`/`skills` JSON object. The package flattens it and
  validates the result against `SkillGraph`.
- An unusable JSON/shape response may receive one parse repair. A structurally invalid graph may
  receive one graph repair. At most three calls are made in total. A reply stopped with
  `finish_reason="length"` fails immediately because another prompt cannot fix a configuration
  that truncated the response.
- Gateway `LLMError` subclasses pass through unchanged. Extraction errors contain no job text or
  model reply.
- Prompts include the selected catalog labels, never catalog IDs, and fence the title, description,
  and catalog separately. Fences grow past any backtick run in the supplied text.

## Catalog

`SkillCatalog` is an async protocol with `all_entries()` and `record(graph)`. `SkillStore` contains
the catalog so future per-preparation persistence can be added without changing extraction.
`InMemorySkillStore` seeds common technologies and records first sightings only. Entries contain
`id`, `root_label`, `node_label`, and immutable `created_at`; they do not contain importance,
difficulty, or `parent_id`. Those belong to a preparation graph. The catalog is lost on restart,
but deterministic IDs remain the same. Trees may differ between preparations; IDs do not.

The prompt catalog is capped at `MAX_CATALOG_ENTRIES_IN_PROMPT` (200). Selection priority is seed
entries, entries under seeded roots, entries under roots used in the current user's preparations,
then all other entries. When a tier must be capped, selection round-robins alphabetically across
roots and takes newest first within each root. `created_at` means first seen, not last used; when
persistent storage or measured prompt pressure makes the cap consequential, add `last_seen_at` in
that storage work and order by it instead.

## Configuration and errors

This package reads no environment variables itself. Its model calls use the supplied `LLM`, which
uses `LLM_BASE_URL`, `LLM_MODEL`, `LLM_CONTEXT_TOKENS`, and `LLM_MAX_OUTPUT_TOKENS` from
`llm_gateway`. Long job descriptions can exceed the default 8192-token context; configure the
context to match the model server and leave room for the output. Never put `.env` values in a
browser variable or commit `.env`.

`ReplyNotJsonError` from `llm_gateway` and contract validation failures are handled by the bounded
repair policy. Truncation raises `SkillExtractionError`; gateway errors are not wrapped.

## Development

```powershell
uv sync --all-packages
uv run pytest packages/skill_graph
```
