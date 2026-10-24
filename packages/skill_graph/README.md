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
        owner_id="user-1",
        job_title="Junior React Developer",
        job_description="Build accessible interfaces with React and TypeScript.",
    )
```

The result is a `contracts.SkillGraph` containing flat `SkillNode` values with `parent_id` links.
Each node ID is computed by `contracts.skill_id`; the model never creates IDs. Leaves carry
preparation-specific importance and expected difficulty, each from 1 to 5.

## How extraction runs

The API developer route is a thin wrapper; the package entry point is `extract_skills`.

```text
POST /v1/dev/extract-skills/raw          apps/api/src/api/dev_skills.py
└─ extract_job_skills_raw()              validates the title and the text/plain body
   └─ _extraction_response()             wraps the LLM in a logging proxy and times the call
      └─ extract_skills()                packages/skill_graph/src/skill_graph/extract.py
         ├─ catalog.all_entries()        store.py
         ├─ select_catalog_entries()     prompt.py
         ├─ build_prompt()               prompt.py
         ├─ _complete()                  extract.py -> llm.complete() -> llm_gateway
         ├─ parse_json_reply()           llm_gateway
         ├─ parse_skill_tree()           extract.py
         │  ├─ _require_object()
         │  ├─ _require_label()
         │  ├─ _flatten_skill()          once per nested skill, recursively
         │  └─ SkillGraph.model_validate()   contracts/skills.py
         └─ catalog.record()             store.py
```

Each step does one job:

1. **Read the catalog.** `catalog.all_entries(owner_id)` returns the shared seed labels plus the
   labels this owner recorded in earlier extractions. The in-memory catalog starts with 12 shared
   seeds such as JavaScript, TypeScript, Node.js, Docker, and Git.
2. **Choose prompt entries.** `select_catalog_entries()` caps the catalog at
   `MAX_CATALOG_ENTRIES_IN_PROMPT` (200), seed entries first, so the model can reuse existing
   labels instead of inventing near-duplicates.
3. **Build the prompt.** `build_prompt()` returns two `ChatMessage`s. The system message states
   the extraction rules; the user message fences the job title, description, and catalog as
   untrusted data. The model is told to return a nested `categories`/`skills` JSON object.
4. **Ask the model.** `_complete()` calls `llm.complete(messages, temperature=0.1)`. The model
   returns text; it may contain JSON directly, in a code fence, or with prose around it.
5. **Read the JSON.** `parse_json_reply()` extracts a JSON value without trusting the rest of
   the reply.
6. **Flatten and identify.** `parse_skill_tree()` requires a non-empty `categories` array (at
   most `MAX_ROOT_CATEGORIES`, 8). For each category it creates a root node with
   `skill_id(root_label, root_label)`, then `_flatten_skill()` walks the children recursively.
   Every node gets its ID from `skill_id(root_label, node_label)`; the model never supplies IDs.
   Depth may not exceed three, and only leaves may carry `importance` and `difficulty`.
7. **Validate the contract.** `SkillGraph.model_validate()` applies the shared rules: unique IDs,
   unique sibling labels, valid parents, root-scoped IDs, 3–30 leaves, and 1–5 metadata on leaves
   only. Any violation raises `SkillGraphValidationError`.
8. **Record and return.** `catalog.record(graph, owner_id)` stores first-seen root and node labels
   in that owner's partition, then the validated graph goes back to the caller.

The read/validate loop has a bounded repair policy:

- an unusable JSON value or wrong shape may receive **one parse repair**;
- a parsed value that fails the graph rules may receive **one graph repair**;
- each repair repeats the original prompt with a correction note and the previous reply fenced as
  untrusted data, so at most **three model calls** are made in total;
- a reply with `finish_reason="length"` fails immediately, because another prompt cannot fix an
  output limit that truncated the reply.

### Grouping is the model's choice

The model chooses the category labels and which skills go under them. The code validates the
shape and the graph rules, not the words. A job description that never says "Backend Development"
can still produce a root with that label if the model decides it is a useful grouping for
Node.js, TypeScript, and Nest.js.

That is intentional: categories are presentation and grouping, not askable skills. A root has
`parent_id=None` and no importance or difficulty. The engine selects only leaves, so a label such
as "Backend Development" is never asked as a question; Node.js and TypeScript are.

The catalog nudges the model toward existing labels, especially the seeded technologies, but it
does not force a taxonomy or a particular root. If category wording must be standardized, that is
a prompt or validation change in this package, not something the current code guarantees.

## Extraction behavior

- The model prompt prefers two levels but accepts depth three. It aims for 8–15 leaf skills; the
  validator accepts 3–30 so a vague job does not waste a repair request. It asks for labels of 1–3
  words and at most 80 characters, although `SkillNode.label` accepts up to 120; the prompt is
  deliberately stricter. It also says each label may appear only once within a category, because
  IDs are root-scoped and a repeated leaf label under two parents collides.
- Gateway `LLMError` subclasses pass through unchanged. Extraction errors contain no job text or
  model reply.
- Prompts include the selected catalog labels, never catalog IDs, and fence the title, description,
  and catalog separately. Fences grow past any backtick run in the supplied text.
- Every model reply is untrusted text: it is parsed defensively and never used to construct IDs,
  paths, or prompts without validation.

## Catalog

`SkillCatalog` is an async protocol with `all_entries(owner_id)` and `record(graph, owner_id)`.
`SkillStore` contains the catalog so future per-preparation persistence can be added without
changing extraction. `InMemorySkillStore` seeds common technologies and records first sightings
only. Entries contain `id`, `root_label`, `node_label`, and immutable `created_at`; they do not
contain importance, difficulty, or `parent_id`. Those belong to a preparation graph. The catalog is
lost on restart, but deterministic IDs remain the same. Trees may differ between preparations; IDs
do not.

Seeds live in the shared `None` partition and every owner reads them. Learned labels live in the
owner's own partition by default, so one user's labels never appear in another user's prompt.
`CatalogSharing` is the extension point for another policy: implement `visible_partitions(owner_id)`
and `write_partition(owner_id)` to share by team, domain, preparation, or a future promotion
threshold. `InMemorySkillCatalog(sharing=...)` accepts such a policy; `PerUserSharing` is the
default. The prompt entry cap applies after the visible partitions are merged. The selected entries are
printed one root per line (`React: Hooks, State`) rather than as JSON; at the 200-entry cap that is
about four times smaller and keeps every label beside its root.

The prompt catalog is capped at `MAX_CATALOG_ENTRIES_IN_PROMPT` (200). Selection priority is seed
entries, entries under seeded roots, entries under roots supplied in `prior_root_labels`, then all
other entries. The caller can pass roots it already knows for this user; the catalog itself is not
global. When a tier must be capped, selection round-robins alphabetically across roots and takes
newest first within each root. `created_at` means first seen, not last used; when persistent storage
or measured prompt pressure makes the cap consequential, add `last_seen_at` in that storage work
and order by it instead.

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
