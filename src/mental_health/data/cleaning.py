"""Thoughts
1. I personally think purpose of cleaning.py is not to actually clean the DataFrame / CSV on its own.
2. Instead It provides Function / method to do it and application init point or some other file imports in and uses it 
3. When i am thinking about cleaning.py i am feeling very hard to write code as in notebook its far too easy 
4. But let me do something ! so there 2-things that must be cleaned before anything else
    - Remove Duplicates 
    - Clip the Negative Hours from Physical Hours towards 0
5. I could create 2 different functions doing these two things on provided DF and thus modified DF .
6. Or Maybe I could just make a class , but i have never seen a class in actual codebase so will use functions for now
7. Starting with the removing duplicates
    """

import pandas as pd
import logging

logger = logging.getLogger(__name__)

def remove_duplicates(raw_df:pd.DataFrame)-> pd.DataFrame:
    """Removes all duplicate rows from DataFrame"""
    df = raw_df.copy()
    
    df = df.drop_duplicates()
    
    return df

def fix_physical_activity_hours(raw_df:pd.DataFrame)->pd.DataFrame:
    """Clips negative physical activity values to zero and records which rows were corrected."""
    df = raw_df.copy()
    
    negative_hours = df[df['Physical_Activity_Hours'] < 0].shape[0]
    if negative_hours > 0: # there were some rows with negative hours , log only then
        logger.warning(f"Total Number of Rows Corrected in Column Physical_Activity_Hours : {negative_hours}")
    # Clip the Negative Values
    df['Physical_Activity_Hours'] = df['Physical_Activity_Hours'].clip(lower=0)

    return df
