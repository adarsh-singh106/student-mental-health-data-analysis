# Shadow-serving audit

- Primary artifact root: `C:\Users\adars\Desktop\One ML\student-mental-health-data-analysis\artifacts`
- Shadow artifact root: `C:\Users\adars\Desktop\One ML\student-mental-health-data-analysis\runtime\shadow-artifacts`
- Requests planned: **500**
- The public API remains configured to return only the primary artifact result.

- Primary /readyz version: `20260908T061824666806Z-4888d94c`

## Evidence

- Successful HTTP responses: **500**
- Failures detected before log comparison: **0**
- New prediction-log rows: **500**
- Rows with both primary and shadow scores: **500**
- Shadow artifact version(s) observed: `['20260908T083535785394Z-ea390f9c']`
- Mean absolute primary-shadow score difference: **0.150538**
- Maximum absolute primary-shadow score difference: **0.724448**
- Mean logged model-path latency, primary/shadow: **10.977 ms / 9.776 ms**
- Shadow prediction failures in server stderr: **0**
- Server stderr path: `C:\Users\adars\Desktop\One ML\student-mental-health-data-analysis\runtime\shadow-audit.stderr.log`

## Result

All responses retained the primary public contract, and every persisted successful request carried a candidate comparison.
