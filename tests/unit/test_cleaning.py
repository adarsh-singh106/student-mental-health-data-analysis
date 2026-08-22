import pandas as pd

from mental_health.data.cleaning import (
    remove_duplicates,
    fix_physical_activity_hours
)


test_data_01 = {
    "Name": ["Ash", "Rahul", "Priya", "Ash", "Priya"],
    "Age": [21, 22, 20, 21, 20],
    "Marks": [85, 92, 78, 85, 78]
}

test_df_01 = pd.DataFrame(test_data_01)


def test_remove_duplicates():
    """Test that duplicate rows are removed."""

    df = test_df_01.copy()

    modified_df = remove_duplicates(df)

    assert modified_df.shape[0] == 3
    assert modified_df.duplicated().sum() == 0


test_data_02 = {
    "Physical_Activity_Hours": [7, 0.6, -3, 0.8, -7.8, -1, 5]
}

test_df_02 = pd.DataFrame(test_data_02)


def test_fix_physical_activity_hours():
    """Test that invalid physical activity hours are fixed."""

    df = test_df_02.copy()

    modified_df = fix_physical_activity_hours(df)

    expected = [7, 0.6, 0, 0.8, 0, 0, 5]
    
    assert modified_df["Physical_Activity_Hours"].tolist() == expected

    # assert len(modified_df['Physical_Activity_Hours_Corrected'] == 1) == 3

