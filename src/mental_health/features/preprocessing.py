"""Builds the unfitted preprocessing ColumnTransformer."""

from sklearn.pipeline import Pipeline

from sklearn.preprocessing import StandardScaler,OrdinalEncoder,OneHotEncoder,FunctionTransformer
from sklearn.compose import ColumnTransformer

# Defined Buckets

numeric_bucket = ['Study_Hours',"Age", "Avg_Daily_Usage_Hours", "Daily_Unlocks", "Physical_Activity_Hours", "Sleep_Hours_Per_Night"]

ordinal_bucket = ["Stress_Level"]

nominal_bucket = ["Gender", "Academic_Level", "Most_Used_Platform", "Purpose_Of_Use"]

country_bucket = ["Country"] # high cardinality, apna alag treatment (dekho ADR 0001)

# Countries frequent enough (>= ~80 rows in the dataset) to be their own signal.
# Everything else — rare countries, the literal "Other" already in the CSV, AND any
# unseen country at serve time — collapses into ONE "Other" bucket. This list is
# frozen from a one-time frequency inspection (a human decision, like the ordinal
# order below), NOT read from data at fit time — so nothing leaks per fit.
# Fixes the old DOUBLE catch-all: previously Country_Other (literal) and
# Country_infrequent_sklearn (max_categories bucket) competed as two "misc" columns.
# See CLOSEOUT 1.4 / ADR 0005.
KNOWN_COUNTRIES = ["Australia", "Canada", "France", "Germany", "India",
                    "Ireland", "Mexico", "Spain", "Turkey", "UK", "USA"]


def _collapse_country(X):
    """Map any country not in KNOWN_COUNTRIES (incl. literal 'Other' and unseen) to 'Other'.

    X is a DataFrame with the single 'Country' column; returns the same shape so the
    OneHotEncoder downstream sees one clean column with a bounded set of categories.
    """
    col = X["Country"].where(X["Country"].isin(KNOWN_COUNTRIES), "Other")
    return col.to_frame()



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
            # First collapse rare/unseen/'Other' into a single 'Other', THEN one-hot.
            # handle_unknown='ignore' is a belt-and-suspenders: after collapse every
            # value is either a KNOWN_COUNTRY or 'Other', so nothing unknown should
            # reach the encoder — but if it did, it becomes all-zeros instead of raising.
            ('collapse', FunctionTransformer(_collapse_country, feature_names_out="one-to-one")),
            ('encode', OneHotEncoder(handle_unknown="ignore")),
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