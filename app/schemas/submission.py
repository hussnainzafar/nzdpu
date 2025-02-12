"""Submission schemas"""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
)

from .enums import SubmissionObjStatusEnum
from .restatements import RestatementCreate, RestatementGetSimple

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class SubmissionBase(BaseModel):
    """
    Base schema for Submission
    """

    table_view_id: int
    revision: Annotated[int, Field(default=1)] = 1
    permissions_set_id: Optional[int] = None
    data_source: Optional[str] = None
    status: Optional[SubmissionObjStatusEnum] = None
    values: dict = {}


class SubmissionWithUnits(SubmissionBase):
    """
    Extended schema that includes units.
    """

    units: dict = {}


class SubmissionPublishResponse(BaseModel):
    """
    Schema for Save Submission Draft response
    """

    id: int
    revision: int
    name: str
    status: SubmissionObjStatusEnum
    restatements: Annotated[
        list[RestatementGetSimple] | None, Field(default=None)
    ]
    model_config = ConfigDict(from_attributes=True)


class SubmissionCreate(SubmissionBase):
    """
    Create schema for Submission
    """

    nz_id: int | None = None


class SubmissionGet(SubmissionWithUnits):
    """
    Submission schema
    """

    id: int
    name: str
    lei: str | None
    nz_id: int
    user_id: Optional[int] = None
    submitted_by: int
    created_on: datetime = datetime.now()
    active: bool = True
    activated_on: datetime = datetime.now()
    checked_out: bool = False
    checked_out_on: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True, extra="allow")

    @field_serializer("values")
    def serialize_dt(self, values: dict):
        keys = [
            "reporting_datetime",
            "date_start_reporting_year",
            "date_end_reporting_year",
        ]
        for key in keys:
            value = values.get(key, None)
            if isinstance(value, datetime):
                values[key] = value.strftime("%Y-%m-%d %H:%M:%S.%f")
        return values


class SubmissionGetWithRestatedFields(SubmissionGet):
    """
    Submission schema with restated_fields to data_source mapping
    """

    restated_fields_data_source: dict | None = None


class DisclosureDetailsResponse(SubmissionGetWithRestatedFields):
    """
    Disclosure Details schema
    """

    last_updated: datetime
    originally_created_on: datetime
    restated_fields_last_updated: dict[str, datetime]


class PublishedSubmissionBase(SubmissionWithUnits):
    """
    Base schema for Submission
    """

    id: int
    table_view_id: int
    name: str
    values: dict
    revision: Annotated[int, Field(default=1)] = 1
    user_id: Optional[int] = None
    checked_out: bool = False
    checked_out_on: Optional[datetime] = None
    permissions_set_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class GetPublicationsResponse(BaseModel):
    """GetPublicationsResponse

    :param _type_ BaseModel: _description_
    """

    publications: list[PublishedSubmissionBase]


class SubmissionEditModeResponse(BaseModel):
    """
    Submission schema for "set edit mode" endpoint.
    """

    id: int
    name: str
    checked_out: bool
    checked_out_on: Optional[datetime] = None
    user_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class AggregatedValidationResponse(BaseModel):
    """
    Schema for Aggregated Validation Response
    """

    offset: int
    limit: int
    total: int
    invalid_submissions: list[dict]


class SubmissionList(BaseModel):
    """
    Schema for list Submissions.
    """

    start: Optional[int] = None
    end: Optional[int] = None
    total: Optional[int] = None
    items: list[SubmissionGet]


class SubmissionRevisionList(BaseModel):
    """
    Schema for list Submissions.
    """

    start: int
    end: int
    total: int
    items: list[SubmissionGet]


class SubmissionUpdate(BaseModel):
    """
    Schema for update Submissions.
    """

    checked_out: bool = False
    checked_out_on: Optional[datetime] = None
    values: dict


class RevisionUpdate(BaseModel):
    """
    Schema for update Submissions.
    """

    data_source: Optional[str] = None
    reporting_datetime: Optional[datetime] = None
    restatements: list[RestatementCreate]
    group_id: Annotated[
        int | None,
        Field(default=None, description="Group id for restatement history"),
    ]


class SubmissionRollback(BaseModel):
    """
    Schema for rollback Submissions.
    """

    active_id: Optional[int] = None
    active_revision: Optional[int] = None
    prev_active_id: Optional[int] = None
    prev_active_revision: Optional[int] = None
    name: str


class LatestReportingYearResponse(BaseModel):
    """
    Schema for Latest Reporting Year API Response
    """

    year: int


class SubmissionDeleteResponse(BaseModel):
    """
    schema for delete revision
    """

    success: bool


class SubmissionDelete(BaseModel):
    """
    schema for delete Submission
    """

    success: bool
    deleted_revisions: int
