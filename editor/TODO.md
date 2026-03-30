# Editor TODO

## YAML round-trip fidelity
`yaml.safe_dump` strips comments from the spec files. The originals have helpful
header comments (e.g. explaining activation modes, condition fields) that will be
lost on first save through the editor. Switch `yaml_io.py` to use `ruamel.yaml`
for comment-preserving round-trips.

## Reordering in sections editor
Subsections and questions within a section can be added and removed but not
reordered. Add up/down arrow buttons (or drag-and-drop) so users can control
the display order.

## DAG click-to-navigate
The DAG page navigates to the correct entity page on node click and passes
`?selected=id` as a query parameter, but the entity pages don't read the query
param to auto-select the entity. Wire up `useSearchParams` in each page.

## Editor backend tests
There are no tests for `editor/backend/`. At minimum, test:
- `yaml_io.read_spec` / `write_spec` round-trip
- `validation.validate_spec` with valid and invalid specs
- API endpoint responses (use FastAPI's `TestClient`)

## Module resolution workaround
`run_editor.py` exists because uvicorn can't resolve `editor.backend.app` as a
module path — the project root isn't on `sys.path` by default. Consider making
the project an installable package or using a `__main__.py` entry point instead.
