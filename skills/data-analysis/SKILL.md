---
name: data-analysis
description: Analyze data files (CSV, JSON, Excel, etc.), compute statistics, and summarize findings. Use for any data exploration or analysis task.
allowed-tools: execute write_file read_file
---

## Data Analysis Skill

### When to Use
- Analyzing CSV, JSON, Excel, or other data files
- Computing statistics or aggregations
- Finding patterns or anomalies in data
- Generating summaries or reports

### Workflow

1. **Inspect** — check file format, size, first few rows
2. **Load** — use appropriate library (pandas, json, csv)
3. **Explore** — shape, columns, dtypes, null counts
4. **Analyze** — compute what's asked
5. **Report** — summarize findings clearly

### Rules

- Install required packages first: `pip3 install pandas openpyxl`
- For large files (>10MB): read in chunks or sample first
- Always check for null/missing values before analysis
- Output results as text — don't assume visualization tools are available
- Disk limit is 10MB — don't write large intermediate files

### Example

```python
import pandas as pd

df = pd.read_csv("data.csv")
print(df.shape)          # rows, columns
print(df.dtypes)         # column types
print(df.isnull().sum()) # missing values
print(df.describe())     # statistics
```
