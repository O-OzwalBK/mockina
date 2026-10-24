# contracts

`contracts` is the shared source of truth for data shapes and validation rules used by the API,
backend packages, and web client. Models are immutable, reject unknown fields, trim surrounding
whitespace, and are exported from `contracts`.

## Skill graphs

`SkillNode` represents a root category, an intermediate node, or a leaf in one preparation.
`SkillGraph` validates the complete tree: parent references, unique IDs and sibling labels, IDs
derived from the root and node labels, a maximum depth of three, and 3–30 leaf skills. Only leaves
carry `importance` and `difficulty`, both on a 1–5 scale. Those values belong to the preparation;
they are not part of a global catalog entry.

`skill_id(root_label, node_label)` returns a deterministic UUIDv5. Its inputs are normalized with
Unicode NFKC, lowercase, punctuation replaced by spaces except `+` and `#`, and collapsed
whitespace. Node labels additionally drop the documented stopwords and sort the remaining tokens.
Root tokens are removed from the sorted node key except for protected compounds such as `React
Native` and `React Router`. The permanent namespace, normalization rules, protected compounds,
and known IDs are pinned by tests. Changing this scheme changes identities and requires a migration
plan for stored `Question.skill_id` values.

Trees may differ between preparations; IDs do not. For example, a skill can be an intermediate
node in one graph and a leaf in another while keeping the same root-scoped ID.

## Generated schemas

The JSON schemas are generated from these models and must not be edited by hand. After changing a
contract, run from the repository root:

```powershell
uv run --locked --all-packages python scripts/export_schemas.py
```

The web client types are generated from `docs/schemas`; regenerate them with
`pnpm generate:api-types` from `apps/web` after contract changes.

## Development

```powershell
uv run pytest packages/contracts
```
