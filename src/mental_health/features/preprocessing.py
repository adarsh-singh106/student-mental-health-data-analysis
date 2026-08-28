"""Builds the unfitted preprocessing ColumnTransformer."""

from sklearn.pipeline import Pipeline

from sklearn.preprocessing import StandardScaler,OrdinalEncoder,OneHotEncoder
from sklearn.compose import ColumnTransformer

# Defined Buckets

numeric_bucket = ['Study_Hours',"Age", "Avg_Daily_Usage_Hours", "Daily_Unlocks", "Physical_Activity_Hours", "Sleep_Hours_Per_Night"]

ordinal_bucket = ["Stress_Level"]

nominal_bucket = ["Gender", "Academic_Level", "Most_Used_Platform", "Purpose_Of_Use"]

country_bucket = ["Country"] # high cardinality, apna alag treatment (dekho ADR 0001)



# preprocessor ColumnTransformer
def build_preprocessor()->ColumnTransformer:
    """Prepare Mini Pipelines and Build ColumnTransformer : """

    # Individual Pipeline for bucket level Transformation

    numeric_pipeline = Pipeline(
        steps=[
            ('scale', StandardScaler())
        ]
    )

    ordinal_pipeline = Pipeline(
        steps=[
            ('encode', OrdinalEncoder(
                categories=[['Low', 'Medium', 'High', 'Very High']]
            ))
        ]
    )


    nominal_pipeline = Pipeline(
        steps=[
            ('encode', OneHotEncoder(
                handle_unknown="ignore"
            ))
        ]
    )

    country_pipeline = Pipeline(
        steps=[
            ('encode', OneHotEncoder(
                handle_unknown="infrequent_if_exist",
                max_categories=11
            ))
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric_pipeline", numeric_pipeline, numeric_bucket),
            ("ordinal_pipeline", ordinal_pipeline, ordinal_bucket),
            ("nominal_pipeline", nominal_pipeline, nominal_bucket),
            ("country_pipeline", country_pipeline, country_bucket)
        ]
    )

    return preprocessor