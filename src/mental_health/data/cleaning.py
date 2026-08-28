

import pandas as pd
import logging

logger = logging.getLogger(__name__)

def remove_duplicates(raw_df:pd.DataFrame)-> pd.DataFrame:
    """Removes all duplicate rows from DataFrame"""
    df = raw_df.copy()
    
    df = df.drop_duplicates()
    
    return df

def fix_physical_activity_hours(raw_df:pd.DataFrame)->pd.DataFrame:
    """Clip negative Physical_Activity_Hours to 0 and log how many rows were fixed."""
    df = raw_df.copy()
    
    negative_hours = df[df['Physical_Activity_Hours'] < 0].shape[0]
    if negative_hours > 0: # there were some rows with negative hours , log only then
        logger.warning("Total Number of Rows Corrected in Column Physical_Activity_Hours : %s",negative_hours)
    # Clip the Negative Values
    df['Physical_Activity_Hours'] = df['Physical_Activity_Hours'].clip(lower=0)

    return df
