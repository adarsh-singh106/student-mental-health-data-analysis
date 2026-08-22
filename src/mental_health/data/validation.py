import logging
from pathlib import Path
from schema import SocialMediaUsageSchema

import pandas as pd
import pandera.pandas as pa

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CSV_PATH = PROJECT_ROOT / 'data' / 'raw' / 'Student Social Media And Mental Health Impact.csv'

# --------------------------------------------------------------------------
# Pipeline-friendly validation entrypoint
# --------------------------------------------------------------------------

def validate_csv(path:str, lazy: bool = True) -> pd.DataFrame:
    """Load & Validate a CSV against SocialMediaUsageSchema.

    lazy=True (default, recommended for pipelines): collects ALL failures
    and logs a structured report before raising, instead of stopping at
    the first bad row.

    Args:
        path (str): _description_
        lazy (bool, optional): _description_. Defaults to True.

    Returns:
        pd.DataFrame: _description_
    """
    df = pd.read_csv(path)

    try:
        validated = SocialMediaUsageSchema.validate(df, lazy=lazy)
        logger.info("Validation passed: %d rows, %d columns", *validated.shape)        
        return validated
    except pa.errors.SchemaErrors as e:
        logger.error(
            "Validation failed with %d failure cases", len(e.failure_cases)
        )
        # Failure cases as a DataFrame: columns include
        # ['schema_context', 'column', 'check', 'check_number',
        #  'failure_case', 'index']
        logger.error("\n%s", e.failure_cases.to_string())
        raise
    except pa.errors.SchemaError as e:
        logger.error("Validation failed (fail-fast): %s", e)
        raise

if __name__ == "__main__":
    validate_csv(CSV_PATH)

