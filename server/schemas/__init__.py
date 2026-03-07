from typing import Optional
from datetime import date as DateType, datetime

from pydantic import BaseModel


class RoleResponse(BaseModel):
    id: int
    name: str
    code: str

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    id: int
    username: str
    roles: list[RoleResponse]

    class Config:
        from_attributes = True


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    revoked: bool
    created_by: str

    class Config:
        from_attributes = True


class DataTypeResponse(BaseModel):
    id: int
    name: str
    code: str

    class Config:
        from_attributes = True


class StationResponse(BaseModel):
    id: int
    name: str
    code: str

    class Config:
        from_attributes = True


class FileResponse(BaseModel):
    id: int
    type_code: str
    station_code: str
    filename: str
    file_path: str
    file_sha256: str
    file_size: int
    total_rows: int | None = None
    date: DateType | None = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class SyncCheckItem(BaseModel):
    filename: str
    sha256: str
    data_type: str
    station: str
    # SDS fields — required when data_type == "seismic"
    net: str | None = None
    loc: str | None = None
    chan: str | None = None
    sds_type: str | None = None
    day: str | None = None  # zero-padded day-of-year, e.g. "001"


class SyncCheckResponse(BaseModel):
    to_upload: list[SyncCheckItem]
