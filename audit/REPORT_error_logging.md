# Structured 500 logging audit

- A temporary manifest-verified artifact is used only for this audit.
- Its pipeline intentionally raises only when POST /predict calls predict().
- The report records whether a trace exists, not the traceback contents.

- Temporary artifact directory: `C:\Users\adars\AppData\Local\Temp\mental-health-error-audit-f86hlken\artifacts\error-audit-v1`
- /readyz returned 200 for temporary version: `error-audit-v1`

## Evidence

- POST /predict status: **500**
- Generic client body preserved: **True**
- X-Request-ID returned: `5f878bba56ba4986a813e722de98f5f0`
- JSON event count in server stderr: **1**
- unhandled_exception event count: **1**
- Event request ID matches response: **True**
- Event exception type: `RuntimeError`
- Event contains traceback: **True**
- Server stderr path: `C:\Users\adars\Desktop\One ML\student-mental-health-data-analysis\runtime\error-audit.stderr.log`

## Result

The real server returned a generic 500 while writing a correlated JSON event with exception type and traceback to stderr.
