from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True


class ApiKeyOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    revoked: bool
    created_by: str

    class Config:
        from_attributes = True


class DataFileOut(BaseModel):
    id: int
    data_type: str
    station: str
    filename: str
    file_path: str
    file_sha256: str
    file_size: int
    total_rows: int | None = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class SyncCheckItem(BaseModel):
    filename: str
    sha256: str
    data_type: str
    station: str
    # SDS fields — required when data_type == "seismic"
    net: Optional[str] = None
    loc: Optional[str] = None
    chan: Optional[str] = None
    sds_type: Optional[str] = None
    day: Optional[str] = None   # zero-padded day-of-year, e.g. "001"


class SyncCheckResponse(BaseModel):
    to_upload: list[SyncCheckItem]
