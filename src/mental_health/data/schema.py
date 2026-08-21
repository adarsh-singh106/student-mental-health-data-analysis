import pandera.pandas as pa
import pandas as pd
from pandera.typing import Series

# valid Constants

VALID_GENDERS = ["Male", "Female"]
 
VALID_ACADEMIC_LEVELS = ["High School", "Undergraduate", "Graduate"]
 
VALID_PLATFORMS = [
    "Facebook", "Instagram", "Snapchat", "Twitter", "YouTube", "TikTok",
    "LinkedIn", "WhatsApp", "WeChat", "VKontakte", "KakaoTalk", "LINE",
]
 
VALID_PURPOSES = ["Networking", "Education", "Entertainment", "News"]
 
VALID_STRESS_LEVELS = ["Low", "Medium", "High", "Very High"]


class SocialMediaUsageSchema(pa.DataFrameModel):
    """Schema for Validating the social media usage survey export."""

    Age:Series[int] = pa.Field(
        ge=13, le=100,
        description="Age in years; Observed range in data is 18-24"
    )

    Gender: Series[str] = pa.Field(
        isin=VALID_GENDERS,
        description="Self-reported gender category"
    )

    Country: Series[str] = pa.Field(
        nullable=False,
        description="Country of residence, or literal 'Other' for unlisted countries"
    )

    Academic_Level: Series[str] = pa.Field(
        isin=VALID_ACADEMIC_LEVELS,
        description="Current Level of academic study"
    )

    Most_Used_Platform: Series[str] = pa.Field(
        isin=VALID_PLATFORMS,
        description="Primary social media platform used"
    )

    Purpose_Of_Use: Series[str] = pa.Field(
        isin=VALID_PURPOSES,
        description="Stated primary reason for social media use"
    )

    Avg_Daily_Usage_Hours: Series[float] = pa.Field(
        ge=0 ,le=24,
        description="Average daily social media usage, in hours"
    )

    Daily_Unlocks: Series[int] = pa.Field(
        ge=0, le=600,
        description="Number of phone unlocks per day"
    )

    Study_Hours: Series[float] = pa.Field(
        ge=0,le=16,
        description="Average daily study time, in hours"
    )

    Physical_Activity_Hours: Series[float] = pa.Field(
        ge=0, le=16,
        description="Average daily physical activity, in hours"
    )

    Sleep_Hours_Per_Night: Series[float] = pa.Field(
        ge=0, le=16,
        description="Average hours of sleep per night"
    )

    Stress_Level: Series[str] = pa.Field(
        isin=VALID_STRESS_LEVELS,
        description="Self-reported categorical stress level"
    )

    Mental_Health_Score: Series[float] = pa.Field(
        ge=0, le=10,
        description="Self-Reported mental health score, 0 (worst) - 10(best)"
    )
    # ----------------------------------------------------------------
    # Configurations
    # ----------------------------------------------------------------
    
    class Config:
        coerce = True     # cast raw CSV strings to declared dtypes
        strict = True      # reject unexpected/extra columns (schema drift)
        ordered = False     # column order isn't semantically meaningful here

    # ----------------------------------------------------------------
    # Cross-column (dataframe-level) checks
    # ----------------------------------------------------------------

    @pa.dataframe_check(
        name="daily_time_budget_within_24h",
        error="Usage + Study + Activity + Sleep hours exceed 24h in a day"
    )
    def daily_time_budget_within_24h(cls, df: pd.DataFrame) -> Series[bool]:
        """A sanity check: nobody has more than 24 hours in a day."""
        total = (
            df["Avg_Daily_Usage_Hours"]
            + df["Study_Hours"]
            + df["Physical_Activity_Hours"]
            + df["Sleep_Hours_Per_Night"]
        )
        return total <= 24