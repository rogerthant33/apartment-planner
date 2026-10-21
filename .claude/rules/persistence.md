---
paths:
  - "src/persistence/**"
  - "src/model/**"
  - "tests/fixtures/**"
---

# Persistence and schema rules

- Any change to a persisted type (`ProjectDoc` and everything inside it) is a
  schema change. Follow the `schema-change` skill. Don't edit the types without
  it.
- Never edit or delete existing files in `tests/fixtures/`. They are the
  record of what old exports look like. Add new ones instead.
- Writes go through the autosave queue. Don't call `put` on `projects` from UI
  code.
- Images are stored only as Blobs in the `assets` store, keyed by
  `[projectId, assetId]`. Base64 exists only inside export files.
- Import never overwrites existing data without an explicit user confirmation
  passed in as an argument. The persistence layer doesn't show dialogs itself.
- Errors are returned or thrown as typed errors with user-readable messages.
  Never swallow them with an empty `catch`.
- Tests use `fake-indexeddb`. Each test gets a fresh database.
