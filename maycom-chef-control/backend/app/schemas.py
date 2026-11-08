from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_version: Literal["v3", "v2.6"] = "v3"
    quality: Literal["standard", "pro"] = "standard"
    character_orientation: Literal["image", "video"] = "video"
    prompt: str = Field(default="", max_length=1500)
    keep_original_sound: bool = True
    trim_start: float = Field(default=0, ge=0, le=297)
    duration: float = Field(default=3, ge=3, le=5)
    output_fps: Literal[24, 30] = 24

    @model_validator(mode="after")
    def validate_duration(self):
        if self.character_orientation == "image" and self.duration > 10:
            raise ValueError("A orientação pela imagem permite no máximo 10 segundos.")
        return self


class CreateJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    character_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    reference_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    settings: GenerationSettings = Field(default_factory=GenerationSettings)
    rights_confirmed: Literal[True]
    fictional_adult_confirmed: Literal[True]
    non_intimate_confirmed: Literal[True]


class ReviewAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "rejected"]
    fictional_adult_confirmed: bool = False
    non_intimate_confirmed: bool = False
