from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PaperProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    proposal_key: str = Field(min_length=1, max_length=120)
    ticker: str = Field(pattern=r"^[A-Za-z0-9.^=-]{1,20}$")
    direction: Literal["long", "short"]
    horizon: Literal["short", "five_years"]
    thesis: str = Field(min_length=20, max_length=20000)
    conviction: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    proposed_entry: Decimal = Field(gt=0, allow_inf_nan=False)
    stop: Decimal = Field(gt=0, allow_inf_nan=False)
    target: Decimal = Field(gt=0, allow_inf_nan=False)
    quantity: Decimal = Field(gt=0, le=1000000, allow_inf_nan=False)
    inference_basis: str = Field(min_length=10, max_length=10000)

    @model_validator(mode="after")
    def valid_levels(self):
        if self.direction == "long" and not self.stop < self.proposed_entry < self.target:
            raise ValueError("Long: stop < entrada propuesta < objetivo")
        if self.direction == "short" and not self.target < self.proposed_entry < self.stop:
            raise ValueError("Short: objetivo < entrada propuesta < stop")
        return self
