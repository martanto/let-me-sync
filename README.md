# Let Me Sync

A FastAPI server for syncing and managing volcano monitoring files. Field clients push data via a bearer-token API; scientists browse and download files through a web dashboard.

## Features

- **DB-driven data types and stations** — managed via admin dashboard, seeded on first run
- **SDS layout for seismic files** — `seismic/YEAR/NET/STA/CHAN.TYPE/NET.STA.LOC.CHAN.TYPE.YEAR.DAY`
- **SHA-256 sync** — clients send a manifest; the server returns only files that are missing or changed
- **Three roles** — `admin`, `uploader`, `downloader`
- **API key auth** for sync clients (Bearer token); session auth for the dashboard
- **Admin dashboard** — manage users, API keys, data types, and stations in-browser

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- SQLite (default, zero-config) **or** PostgreSQL

## Installation

```bash
git clone https://github.com/martanto/let-me-sync
cd let-me-sync
uv sync
```

Copy the environment file and set your values:

```bash
cp .env.example .env
```

| Variable       | Default                                            | Description                         |
|----------------|----------------------------------------------------|-------------------------------------|
| `SECRET_KEY`   | `change-me-in-production-please`                   | Session signing key                 |
| `DEBUG`        | `false`                                            | Seed test data on startup           |
| `APP_ENV`      | `development`                                      | Set to `production` to disable seed |
| `DATABASE_URL` | `sqlite:///./server/database/data.db` (auto)       | SQLAlchemy database URL             |

## Database

The server defaults to **SQLite** — no setup needed, the file is created automatically on first run.

Schema migrations are managed by **Alembic** and run automatically on startup. To run them manually:

```bash
uv run alembic upgrade head
```

### Using PostgreSQL instead

Create the database, then set `DATABASE_URL` in your `.env`:

```bash
psql -U postgres -c "CREATE DATABASE let_me_sync;"
```

```env
DATABASE_URL=postgresql://postgres@localhost:5432/let_me_sync
```

## Running

```bash
uv run let-me-sync
```

On the **first run** with no users in the database, the server will prompt you to create an admin account interactively.

With `DEBUG=true` the server seeds three test accounts and a pre-generated API key instead of prompting:

| Username     | Password       | Role         |
|--------------|----------------|--------------|
| `admin`      | `admin123`     | admin        |
| `uploader`   | `uploader123`  | uploader     |
| `downloader` | `downloader123`| downloader   |

The dev API key token is printed to the console on startup.

## Project Structure

```
alembic/                      # Alembic migration environment
  versions/                   # Migration scripts
  env.py                      # Connects Alembic to the app's models and DATABASE_URL
alembic.ini                   # Alembic configuration (URL set dynamically in env.py)

server/
├── main.py                  # App entry point, lifespan, reference data seeding, middleware wiring
├── middleware.py             # Session + Bearer auth, role checks, redirect-to-login for unauthenticated
├── config/__init__.py        # DATA_ROOT, DATA_TYPES, DATABASE_URL, environment settings
├── database/connection.py    # SQLAlchemy engine, SessionLocal, check_db_connection()
├── models/__init__.py        # Role, User, ApiKey, DataType, Station, File
├── schemas/__init__.py       # Pydantic response models (*Response suffix)
├── cli/
│   ├── seed.py               # Dev seed: roles, users, API key, dummy files
│   └── refresh.py            # Alembic downgrade+upgrade + re-seed (dev only)
├── routes/
│   ├── auth.py               # /login, /logout
│   ├── files.py              # Dashboard, file listing, download, delete, upload
│   ├── sync.py               # /sync/check, /sync/upload
│   └── admin.py              # Users, API keys, data types, stations management
├── utils/helpers.py          # SHA-256, token generation, path builders, slugify
├── static/style.css          # UI stylesheet
└── templates/                # Jinja2 templates
    ├── base.html
    ├── login.html
    ├── index.html
    ├── files.html
    ├── users.html
    ├── api_keys.html
    ├── data_types.html
    └── stations.html

uploads/                      # Stored files (inside server/)
  seismic/YEAR/NET/STA/CHAN.TYPE/NET.STA.LOC.CHAN.TYPE.YEAR.DAY
  deformation/STATION/YEAR/FILENAME
  multigas/STATION/YEAR/FILENAME
  visual/STATION/YEAR/FILENAME
  weather/STATION/YEAR/FILENAME
  paper/STATION/YEAR/FILENAME
```

## Database Schema

| Table        | Description                                                       |
|--------------|-------------------------------------------------------------------|
| `users`      | User accounts with hashed passwords                               |
| `roles`      | `admin`, `uploader`, `downloader`                                 |
| `user_roles` | Many-to-many join between users and roles                         |
| `api_keys`   | Bearer tokens (SHA-256 hashed)                                    |
| `data_types` | Reference table for file categories (e.g. seismic, weather)       |
| `stations`   | Reference table for monitoring stations (e.g. sta1–sta5)          |
| `files`      | Uploaded file records; FK to `data_types.code` and `stations.code`|

`data_types` and `stations` are seeded automatically on every startup.

## File Storage

### Seismic — SDS layout

Seismic files follow the [SeisComP Data Structure (SDS)](https://www.seiscomp.de/doc/apps/slarchive.html):

```
seismic/
└── YEAR/
    └── NET/
        └── STA/
            └── CHAN.TYPE/
                └── NET.STA.LOC.CHAN.TYPE.YEAR.DAY
```

Example: `seismic/2024/VG/STA1/EHZ.D/VG.STA1..EHZ.D.2024.001`

### Other data types

```
deformation/STA1/2024/2024-01-15.csv
multigas/STA3/2024/2024-01-15.csv
visual/STA1/2024/cam01_2024001.jpg
weather/STA2/2024/2024-01-15.csv
paper/STA1/2024/research_2024.pdf
```

Weather and deformation files must be named `YYYY-MM-DD.csv`.

## API Reference

All sync endpoints require `Authorization: Bearer <token>`.

### `POST /sync/check`

Send a manifest of local files. The server responds with the subset that needs to be uploaded (missing or hash mismatch).

**Request body** — JSON array:

```json
[
  {
    "filename": "VG.STA1..EHZ.D.2024.001",
    "sha256": "a3f...",
    "data_type": "seismic",
    "station": "sta1",
    "net": "VG",
    "loc": "",
    "chan": "EHZ",
    "sds_type": "D",
    "day": "001"
  },
  {
    "filename": "2024-01-15.csv",
    "sha256": "b7c...",
    "data_type": "deformation",
    "station": "sta1"
  }
]
```

`net`, `loc`, `chan`, `sds_type`, `day` are only required when `data_type` is `seismic`.

**Response:**

```json
{
  "to_upload": [
    { "filename": "VG.STA1..EHZ.D.2024.001", "sha256": "a3f...", ... }
  ]
}
```

### `POST /sync/upload`

Upload a single file. Use `multipart/form-data`.

**Form fields:**

| Field       | Required          | Description                                       |
|-------------|-------------------|---------------------------------------------------|
| `file`      | always            | File content                                      |
| `data_type` | always            | e.g. `seismic`, `deformation`, `weather`          |
| `station`   | always            | Station code (e.g. `sta1`)                        |
| `date`      | non-seismic       | File date `YYYY-MM-DD` (auto-derived for CSV/seismic) |
| `net`       | seismic only      | Network code                                      |
| `loc`       | seismic only      | Location code (may be empty)                      |
| `chan`      | seismic only      | Channel code, e.g. `EHZ`                         |
| `sds_type`  | seismic only      | SDS record type, e.g. `D`                        |
| `day`       | seismic only      | Day of year, zero-padded, e.g. `001`             |

**Response:**

```json
{ "status": "created", "id": 7, "sha256": "0f0f..." }
```

`status` is `created` for new records or `updated` when an existing file is replaced.

### `GET /files`

Returns a JSON list of all stored file records. Accepts optional query params `data_type` and `station`.

```bash
curl http://localhost:8000/files?data_type=seismic \
  -H "Authorization: Bearer <token>"
```

### `GET /download/{id}`

Download a file by its database ID (session or Bearer auth).

### `GET /download-zip?ids=1&ids=2`

Download multiple files as a ZIP archive (session or Bearer auth).

### `POST /files/{id}/delete`

Delete a file record and its data from disk. Admin only (POST form, session auth).

## Web Dashboard

| Route                  | Access  | Description                                      |
|------------------------|---------|--------------------------------------------------|
| `/`                    | all     | Data group cards with file counts                |
| `/files/{type}`        | all     | File listing with station filter and pagination  |
| `/admin/users`         | admin   | Create, delete, change passwords                 |
| `/admin/api-keys`      | admin   | Generate, revoke, delete API keys                |
| `/admin/data-types`    | admin   | Manage data type definitions                     |
| `/admin/stations`      | admin   | Manage station definitions                       |

## Authentication

**Dashboard** — form login at `/login`, session cookie (`lms_session`). All unauthenticated requests redirect to `/login`.

**API clients** — `Authorization: Bearer <token>` header. Tokens are generated by an admin in the dashboard. The raw token is shown once; the server stores only its SHA-256 hash. Requests to bearer-only endpoints without a valid token return `401` if the client accepts JSON, otherwise redirect to `/login`.

Revoked keys are rejected immediately.

## License

MIT
