# Schema-breakage audit

- Source CSV: `C:\Users\adars\Desktop\One ML\student-mental-health-data-analysis\data\raw\Student Social Media And Mental Health Impact.csv`
- The source file was read once and was not modified.
- Baseline shape: **5000 rows x 13 columns**

- Baseline prepare_data result: **accepted (4998 rows x 13 columns)**

### Unexpected column

- Mutation: Added `Audit_Unexpected_Column`; production schemas often receive this after an upstream export adds a field.
- Rejected at: **structural column contract**
- Exception: `DataContractError before cleaning`
- Evidence: `Raw dataset column contract failed: unexpected=['Audit_Unexpected_Column']`
- sklearn training/transform/prediction reached: **no**

### Missing cleaning dependency

- Mutation: Deleted `Physical_Activity_Hours`; the cleaning step normally indexes this exact column.
- Rejected at: **structural column contract**
- Exception: `DataContractError before cleaning`
- Evidence: `Raw dataset column contract failed: missing=['Physical_Activity_Hours']`
- sklearn training/transform/prediction reached: **no**

### Non-numeric Age

- Mutation: Replaced one Age value with `not-an-integer`, forcing CSV parsing to produce a non-coercible value rather than a harmless numeric string.
- Rejected at: **Pandera dataframe validation**
- Exception: `SchemaErrors with 4 failure case(s) after cleaning`
- Evidence: `[{"schema_context": "Column", "column": "Age", "check": "coerce_dtype('int64')", "check_number": null, "failure_case": "not-an-integer", "index": 0}, {"schema_context": "Column", "column": "Age", "check": "dtype('int64')", "check_number": null, "failure_case": "not-an-integer", "index": 0}, {"schema`
- sklearn training/transform/prediction reached: **no**

## Summary

| Mutation | Expected boundary | Why it matters |
|---|---|---|
| Extra column | Structural contract before cleaning | Rejects schema drift explicitly instead of silently ignoring a field. |
| Missing `Physical_Activity_Hours` | Structural contract before cleaning | Prevents a later cleaning `KeyError` that obscures the data-contract cause. |
| Non-numeric `Age` | Pandera validation after cleaning | Catches semantic type corruption before sklearn receives the frame. |

These experiments call `prepare_data()` only. A successful schema boundary does not prove downstream model quality; it proves malformed CSVs are stopped before the training pipeline can use them.
