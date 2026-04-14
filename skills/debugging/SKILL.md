---
name: debugging
description: Diagnose and fix errors in code. Use when code fails, produces wrong output, or throws exceptions.
allowed-tools: execute read_file write_file edit_file
---

## Debugging Skill

### When to Use
- Code throws an exception or error
- Output is wrong or unexpected
- Program hangs or times out

### Workflow

1. **Read the error** — identify exception type, line number, message
2. **Isolate** — reproduce with minimal code
3. **Hypothesize** — one cause at a time
4. **Fix** — targeted change, not rewrite
5. **Verify** — run again and confirm fix

### Rules

- Read error messages carefully before changing anything
- Fix one thing at a time — don't change multiple things simultaneously
- Add `print()` statements to trace values if needed
- If timeout (exit_code=124): the code has infinite loop or is too slow — add limits
- If memory error (exit_code=1 + MemoryError): reduce data size or use streaming
- Don't rewrite working code to fix one bug

### Common Patterns

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `ModuleNotFoundError` | Package not installed | `pip3 install <pkg>` |
| `FileNotFoundError` | Wrong path | Check with `ls` |
| `PermissionError` | Read-only path | Write to `/tmp` or workdir |
| `TimeoutExpired` (124) | Infinite loop / slow | Add termination condition |
| `MemoryError` | Data too large | Process in chunks |
