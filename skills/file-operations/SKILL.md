---
name: file-operations
description: Read, write, edit, and manage files in the sandbox workspace. Use for any file creation, modification, or inspection tasks.
allowed-tools: read_file write_file edit_file ls glob grep
---

## File Operations Skill

### When to Use
- Creating or modifying files
- Searching file contents
- Listing directory structure
- Reading configuration or data files

### Workflow

1. **Explore first** — use `ls` or `glob` to understand the directory structure
2. **Read before edit** — always `read_file` before `edit_file`
3. **Write atomically** — use `write_file` for new files, `edit_file` for modifications
4. **Verify** — read back after writing to confirm

### Rules

- Never overwrite files without reading them first
- Use `grep` to search content across multiple files
- Use `glob` to find files by pattern (e.g., `**/*.py`)
- Keep paths relative to the working directory
- Large files: read with `limit` and `offset` to avoid context overflow

### Example

```
ls(".")                          # explore structure
read_file("config.json")         # read before editing
edit_file("config.json", ...)    # targeted edit
read_file("config.json")         # verify change
```
