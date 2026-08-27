"""
Purpose of the test :
1. First check if prepare_data() is working with a dummy dataset  
2. Then Check using smaller peice of genrated dataset that has actual bugs and verfy it 
    output against the correct expected output
"""
from pathlib import Path

from mental_health.data.preparation import prepare_data

path = Path(__file__).parent / "fixtures" / "preparation_input.csv"

def test_preparation():

    provided_df = prepare_data(path)


    assert provided_df.shape[0] == 9

    assert provided_df['Physical_Activity_Hours'].min() >= 0

    

