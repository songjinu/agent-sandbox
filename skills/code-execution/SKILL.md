---
name: code-execution
description: Run code safely in the sandbox. Use for executing Python, shell commands, scripts, or any code that needs to be run and verified.
allowed-tools: execute write_file read_file
---

## Code Execution Skill

### When to Use
- User asks to run, test, or execute code
- Need to verify output of a program
- Installing packages or running scripts

### Workflow

1. **Write code to a file first** — don't run inline unless it's a one-liner
2. **Execute** — use `execute` tool to run
3. **Check output** — verify exit code and stdout/stderr
4. **Iterate** — fix errors and re-run until correct

### Rules

- Always check `exit_code` — non-zero means failure
- For Python: prefer `python3 script.py` over `python3 -c "..."`
- Install packages with `pip3 install <pkg>` before importing
- Use `/tmp` for temporary files, working directory for outputs
- If execution times out (exit_code=124), simplify or split the task

### Example

```
write_file("solution.py", "print('hello')")
execute("python3 solution.py")
# Check: exit_code==0, output contains "hello"
```
