"""Core job is to take all ./ files and orchestrate them and in the end return a DF which can be used further

So Now for data preparation 
the first thing i would need is data itself ! and i think i must not hard code the path . as there could be different path
so instead i can just ask for the data or the path itself . let me see which one would be best . 
i think i should take the path and load data as loading the data is my responsiblity !so even if i am getting DF then that program has to read it"""

import pandas as pd


from mental_health.data.cleaning import fix_physical_activity_hours,remove_duplicates
from mental_health.data.validation import validate_df


def load_data(path:str)-> pd.DataFrame:
    ## Load the data & if path invalid raise error
    try:
        raw_df = pd.read_csv(path)
        return raw_df
    except FileNotFoundError as e:
        print("Invalid Path Error: ",e)
        raise
    except Exception as e:
        print("Error : ", e)
        raise


def prepare_data(path:str)->pd.DataFrame:
    raw_df = load_data(path)

    ## apply cleaning
    raw_df = remove_duplicates(raw_df) 
    raw_df = fix_physical_activity_hours(raw_df)
    

    ## validate again
    validated_DF = validate_df(raw_df)
    
    return validated_DF