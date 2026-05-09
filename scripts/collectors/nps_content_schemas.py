"""Pydantic schemas for NPS content API responses.

Validates and normalizes data from the /thingstodo and /places endpoints.
HTML tags are stripped from description fields during validation.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class _HTMLStripper(HTMLParser):
    """Simple HTML tag stripper using stdlib html.parser."""

    def __init__(self) -> None:
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self._fed: list[str] = []

    def handle_data(self, d: str) -> None:
        self._fed.append(d)

    def get_data(self) -> str:
        return "".join(self._fed)


def strip_html(value: str) -> str:
    """Strip HTML tags from a string, returning plain text."""
    if not value:
        return value
    stripper = _HTMLStripper()
    stripper.feed(value)
    result = stripper.get_data()
    # Collapse multiple whitespace into single spaces
    result = re.sub(r"\s+", " ", result).strip()
    return result


class NPSThingsToDoResponse(BaseModel):
    """Validates a single item from the NPS /thingstodo API endpoint."""

    id: str = Field(..., description="Unique identifier from NPS API")
    title: str = Field(..., description="Activity title")
    short_description: str | None = Field(
        None, alias="shortDescription", description="Brief description"
    )
    long_description: str | None = Field(
        None, alias="longDescription", description="Full description"
    )
    tags: list[str] = Field(default_factory=list, description="Associated tags")
    related_parks: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="relatedParks",
        description="Parks where this activity is available",
    )
    activities: list[dict[str, Any]] = Field(
        default_factory=list, description="Activity types"
    )
    topics: list[dict[str, Any]] = Field(
        default_factory=list, description="Topic categories"
    )
    season: list[str] = Field(
        default_factory=list, description="Seasons when available"
    )
    duration: str | None = Field(None, description="Typical duration")
    pets_description: str | None = Field(
        None, alias="petsDescription", description="Pet policy details"
    )
    are_pets_permitted: str | None = Field(
        None, alias="arePetsPermitted", description="Whether pets are allowed"
    )
    fee_description: str | None = Field(
        None, alias="feeDescription", description="Fee information"
    )
    is_reservation_required: str | None = Field(
        None, alias="isReservationRequired", description="Reservation requirements"
    )
    do_fees_apply: str | None = Field(
        None, alias="doFeesApply", description="Whether fees apply"
    )
    accessibility_information: str | None = Field(
        None, alias="accessibilityInformation", description="Accessibility details"
    )
    latitude: str | None = Field(None, description="Latitude coordinate")
    longitude: str | None = Field(None, description="Longitude coordinate")
    url: str | None = Field(None, description="NPS webpage URL")

    model_config = {"populate_by_name": True}

    @field_validator(
        "short_description",
        "long_description",
        "pets_description",
        "fee_description",
        "accessibility_information",
        mode="before",
    )
    @classmethod
    def strip_html_tags(cls, v: str | None) -> str | None:
        """Strip HTML tags from description fields."""
        if v is None or v == "":
            return v
        return strip_html(str(v))

    @model_validator(mode="after")
    def validate_coordinates(self) -> NPSThingsToDoResponse:
        """Validate coordinate values if present."""
        for attr_name, low, high in [
            ("latitude", -90.0, 90.0),
            ("longitude", -180.0, 180.0),
        ]:
            val = getattr(self, attr_name)
            if val is not None and val != "":
                try:
                    num = float(val)
                    if not (low <= num <= high):
                        setattr(self, attr_name, None)
                except (ValueError, TypeError):
                    setattr(self, attr_name, None)
        return self

    def get_park_codes(self) -> list[str]:
        """Extract park codes from relatedParks."""
        codes = []
        for park in self.related_parks:
            code = park.get("parkCode", "")
            if code:
                codes.append(code.lower())
        return codes


class NPSPlaceResponse(BaseModel):
    """Validates a single item from the NPS /places API endpoint."""

    id: str = Field(..., description="Unique identifier from NPS API")
    title: str = Field(..., description="Place title")
    short_description: str | None = Field(
        None, alias="listingDescription", description="Listing description"
    )
    body_text: str | None = Field(None, alias="bodyText", description="Full body text")
    audio_description: str | None = Field(
        None, alias="audioDescription", description="Audio description text"
    )
    tags: list[str] = Field(default_factory=list, description="Associated tags")
    related_parks: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="relatedParks",
        description="Parks where this place is located",
    )
    latitude: str | None = Field(None, description="Latitude coordinate")
    longitude: str | None = Field(None, description="Longitude coordinate")
    url: str | None = Field(None, description="NPS webpage URL")

    model_config = {"populate_by_name": True}

    @field_validator(
        "short_description",
        "body_text",
        "audio_description",
        mode="before",
    )
    @classmethod
    def strip_html_tags(cls, v: str | None) -> str | None:
        """Strip HTML tags from text fields."""
        if v is None or v == "":
            return v
        return strip_html(str(v))

    @model_validator(mode="after")
    def validate_coordinates(self) -> NPSPlaceResponse:
        """Validate coordinate values if present."""
        for attr_name, low, high in [
            ("latitude", -90.0, 90.0),
            ("longitude", -180.0, 180.0),
        ]:
            val = getattr(self, attr_name)
            if val is not None and val != "":
                try:
                    num = float(val)
                    if not (low <= num <= high):
                        setattr(self, attr_name, None)
                except (ValueError, TypeError):
                    setattr(self, attr_name, None)
        return self

    def get_park_codes(self) -> list[str]:
        """Extract park codes from relatedParks."""
        codes = []
        for park in self.related_parks:
            code = park.get("parkCode", "")
            if code:
                codes.append(code.lower())
        return codes
