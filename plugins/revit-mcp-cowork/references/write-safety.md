# Revit MCP Next Write Safety

## Supported operation groups

- Datums and shell: `create_level`, `create_grid`, `create_wall`, `create_floor`, `create_room`.
- Families and annotation: `load_family`, `place_family_instance`, `create_text_note`, `tag_room`, `tag_element`.
- Documentation: `create_sheet`, `place_view_on_sheet`, `create_schedule`, `add_schedule_field`, `place_schedule_on_sheet`.
- Existing elements: `set_parameter`, `move_element`, `rotate_element`, `copy_element`, `change_element_type`, `set_element_pinned`, `delete_element`.

## Required sequence

1. Read `documentFingerprint` and generation.
2. Discover IDs and writable metadata with focused reads.
3. Preview a bounded transaction.
4. Review `ready`, `changes`, warnings, risk, and dependent deletes.
5. Apply the identical operations with exact preview metadata.
6. Verify with read-only tools.

Use explicit units in coordinates and dimensions. Use `expectedUniqueId` on
existing-element writes and `expectedHostUniqueId` for hosted placement when
available.

## Recovery

- Blocked preview: fix the reported prerequisite and preview again.
- Generation mismatch: refresh model reads and rebuild the change set.
- Missing or expired token: preview again; never synthesize token fields.
- Dependent delete: review the full previewed delete set and obtain user approval.
- Timeout or unknown commit: stabilize the connection and inspect state before retrying.
