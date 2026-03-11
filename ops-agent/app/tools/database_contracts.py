from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.tools.contracts import validate_incident_key


class GetIncidentByKeyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_key: str

    @field_validator("incident_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        validate_incident_key(value)
        return value


class GetIncidentEvidenceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_key: str
    limit: int = Field(default=200, ge=1, le=1000)

    @field_validator("incident_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        validate_incident_key(value)
        return value


class GetIncidentServicesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_key: str

    @field_validator("incident_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        validate_incident_key(value)
        return value


class GetSimilarIncidentsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_key: str
    limit: int = Field(default=5, ge=1, le=50)

    @field_validator("incident_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        validate_incident_key(value)
        return value


class GetResolutionsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_key: str

    @field_validator("incident_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        validate_incident_key(value)
        return value


class ServiceScopedArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(min_length=1)


class LoadSessionMessagesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    limit: int = Field(default=30, ge=1, le=200)


class SaveAssistantMessageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    content_text: str = Field(min_length=1)
    structured_json: dict
