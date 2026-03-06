from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, BigInteger, ForeignKey, Table
from sqlalchemy.orm import relationship
from server.database.connection import Base


user_roles = Table(
    "user_roles", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # "Admin"
    code = Column(String, unique=True, nullable=False)  # "admin"
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
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked = Column(Boolean, default=False)
    created_by = Column(String, nullable=False)


class DataFile(Base):
    __tablename__ = "data_files"

    id = Column(Integer, primary_key=True, index=True)
    data_type = Column(String, nullable=False, index=True)  # seismic | deformation | multigas | visual | weather
    station = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False, unique=True)
    file_sha256 = Column(String, nullable=False)
    file_size = Column(BigInteger, default=0)
    total_rows = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
