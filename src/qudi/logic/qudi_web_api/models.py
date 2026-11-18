from pydantic import BaseModel, Field
# Pydantic automatically checks whether the received parameters are valid

class MeasurementParameters(BaseModel):

    start_voltage: float = Field(
        ge=-10,
        le=10
    )

    stop_voltage: float = Field(
        ge=-10,
        le=10
    )

    number_of_points: int = Field(
        ge=1,
        le=10000
    )

    integration_time: float = Field(
        gt=0,
        le=100
    )

    repetitions: int = Field(
        ge=1,
        le=1000
    )