import logging
from .schema import SocialMediaUsageSchema
import pandas as pd
import pandera.pandas as pa

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Pipeline-friendly validation entrypoint
# --------------------------------------------------------------------------

def validate_df(raw_df:pd.DataFrame, lazy: bool = True) -> pd.DataFrame:
    """Validate a DataFrame against SocialMediaUsageSchema.

    lazy=True (default, recommended for pipelines): collects ALL failures
    and logs a structured report before raising, instead of stopping at
    the first bad row.

    Args:
        raw_df (pd.DataFrame): Raw DataFrame coming from an source
        lazy (bool, optional): Don't Stop at first issue in DF. Defaults to True.

    Returns:
        pd.DataFrame: _description_
    """
    df = raw_df.copy()

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



