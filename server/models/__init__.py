from datetime import UTC, datetime

from sqlalchemy import (
    Date,
    Table,
    Column,
    String,
    Boolean,
    Integer,
    DateTime,
    BigInteger,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from server.database.connection import Base


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    code = Column(String, unique=True, nullable=False)
    users = relationship("User", secondary=user_roles, back_populates="roles")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    roles = relationship("Role", secondary=user_roles, back_populates="users")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    key_hash = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now(UTC))
    revoked = Column(Boolean, default=False)
    created_by = Column(String, nullable=False)


class DataType(Base):
    __tablename__ = "data_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    code = Column(String, unique=True, nullable=False)
    files = relationship("File", back_populates="data_type_rel", passive_deletes=True)


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    code = Column(String, unique=True, nullable=False)
    files = relationship("File", back_populates="station_rel", passive_deletes=True)


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    type_code = Column(
        String,
        ForeignKey("data_types.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    station_code = Column(
        String,
        ForeignKey("stations.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False, unique=True)
    file_sha256 = Column(String, nullable=False)
    file_size = Column(BigInteger, default=0)
    total_rows = Column(Integer, nullable=True)
    date = Column(Date, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.now(UTC))

    data_type_rel = relationship("DataType", back_populates="files")
    station_rel = relationship("Station", back_populates="files")
