"""Request and response schemas for model serving."""


from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mental_health.data.schema import (
    VALID_ACADEMIC_LEVELS,
    VALID_GENDERS,
    VALID_PLATFORMS,
    VALID_PURPOSES,
    VALID_STRESS_LEVELS,
)


def _validate_choice(value: str, valid_values: list[str], field_name: str) -> str:
    if value not in valid_values:
        allowed = ", ".join(valid_values)
        raise ValueError(f"{field_name} must be one of: {allowed}")
    return value


class PredictionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "Age": 20,
                "Gender": "Male",
                "Country": "India",
                "Academic_Level": "Undergraduate",
                "Most_Used_Platform": "Instagram",
                "Purpose_Of_Use": "Education",
                "Avg_Daily_Usage_Hours": 3.0,
                "Daily_Unlocks": 80,
                "Study_Hours": 6.0,
                "Physical_Activity_Hours": 1.0,
                "Sleep_Hours_Per_Night": 8.0,
                "Stress_Level": "Medium",
            }
        },
    )

    Age: int = Field(ge=13, le=100)
    Gender: str
    Country: str = Field(min_length=1, max_length=56)
    Academic_Level: str
    Most_Used_Platform: str
    Purpose_Of_Use: str
    Avg_Daily_Usage_Hours: float = Field(ge=0, le=24)
    Daily_Unlocks: int = Field(ge=0, le=600)
    Study_Hours: float = Field(ge=0, le=16)
    Physical_Activity_Hours: float = Field(ge=0, le=16)
    Sleep_Hours_Per_Night: float = Field(ge=0, le=16)
    Stress_Level: str

    @field_validator("Gender")
    @classmethod
    def validate_gender(cls, value: str) -> str:
        return _validate_choice(value, VALID_GENDERS, "Gender")

    @field_validator("Academic_Level")
    @classmethod
    def validate_academic_level(cls, value: str) -> str:
        return _validate_choice(value, VALID_ACADEMIC_LEVELS, "Academic_Level")

    @field_validator("Most_Used_Platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        return _validate_choice(value, VALID_PLATFORMS, "Most_Used_Platform")

    @field_validator("Purpose_Of_Use")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        return _validate_choice(value, VALID_PURPOSES, "Purpose_Of_Use")

    @field_validator("Stress_Level")
    @classmethod
    def validate_stress_level(cls, value: str) -> str:
        return _validate_choice(value, VALID_STRESS_LEVELS, "Stress_Level")

    @model_validator(mode="after")
    def validate_daily_time_budget(self) -> "PredictionRequest":
        total = (
            self.Avg_Daily_Usage_Hours
            + self.Study_Hours
            + self.Physical_Activity_Hours
            + self.Sleep_Hours_Per_Night
        )
        if total > 24:
            raise ValueError(
                "Avg_Daily_Usage_Hours + Study_Hours + "
                "Physical_Activity_Hours + Sleep_Hours_Per_Night must be <= 24"
            )
        return self


class PredictionResponse(BaseModel):
    mental_health_score: float = Field(ge=0, le=10)
    model_version: str
    note: str = "Educational estimate only; not a diagnosis or clinical assessment."
