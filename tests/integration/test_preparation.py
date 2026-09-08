"""
Purpose of the test :
1. First check if prepare_data() is working with a dummy dataset  
2. Then Check using smaller peice of genrated dataset that has actual bugs and verfy it 
    output against the correct expected output
"""
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
import pytest

from mental_health.data.preparation import prepare_data
from mental_health.data.schema import DataContractError

path = Path(__file__).parent / "fixtures" / "preparation_input.csv"

def test_preparation():

    provided_df = prepare_data(path)


    assert provided_df.shape[0] == 9

    assert provided_df['Physical_Activity_Hours'].min() >= 0


def test_preparation_rejects_missing_column_before_cleaning(tmp_path):
    broken_df = pd.read_csv(path).drop(columns=["Physical_Activity_Hours"])
    broken_path = tmp_path / "missing-column.csv"
    broken_df.to_csv(broken_path, index=False)

    with pytest.raises(DataContractError, match="Physical_Activity_Hours"):
        prepare_data(broken_path)


def test_preparation_rejects_unexpected_column_before_cleaning(tmp_path):
    broken_df = pd.read_csv(path).assign(Audit_Unexpected_Column="unexpected")
    broken_path = tmp_path / "unexpected-column.csv"
    broken_df.to_csv(broken_path, index=False)

    with pytest.raises(DataContractError, match="Audit_Unexpected_Column"):
        prepare_data(broken_path)


def test_preparation_rejects_non_coercible_age_during_pandera_validation(tmp_path):
    broken_df = pd.read_csv(path)
    broken_df["Age"] = broken_df["Age"].astype(object)
    broken_df.loc[0, "Age"] = "not-an-integer"
    broken_path = tmp_path / "non-numeric-age.csv"
    broken_df.to_csv(broken_path, index=False)

    with pytest.raises(pa.errors.SchemaErrors, match="Age"):
        prepare_data(broken_path)

    

