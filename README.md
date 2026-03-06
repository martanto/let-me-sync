# Let Me Sync

A FastAPI server for syncing and managing volcano monitoring files. Field clients push data via a bearer-token API; scientists browse and download files through a web dashboard.

## Features

- **Five data groups** — Seismic, Deformation, Multigas, Visual, Weather
- **SDS layout for seismic files** — `seismic/YEAR/NET/STA/CHAN.TYPE/NET.STA.LOC.CHAN.TYPE.YEAR.DAY`
- **SHA-256 sync** — clients send a manifest; the server returns only files that are missing or changed
- **Three roles** — `admin`, `uploader`, `downloader`
- **API key auth** for sync clients (Bearer token); session auth for the dashboard
- **Admin dashboard** — manage users and API keys in-browser

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

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

| Variable     | Default                          | Description                        |
|--------------|----------------------------------|------------------------------------|
| `SECRET_KEY` | `change-me-in-production-please` | Session signing key                |
| `DEBUG`      | `false`                          | Seed test data on startup          |
| `APP_ENV`    | `development`                    | Set to `production` to disable seed|

## Running

```bash
uv run uvicorn server.main:app --reload
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
server/
├── main.py                  # App entry point, lifespan, middleware wiring
├── middleware.py             # Session + Bearer auth, role checks
├── config/__init__.py        # DATA_ROOT, DATA_TYPES, environment settings
├── database/connection.py    # SQLAlchemy engine, SessionLocal
├── models/__init__.py        # User, ApiKey, DataFile
├── schemas/__init__.py       # Pydantic request/response models
├── routes/
│   ├── auth.py               # /login, /logout
│   ├── files.py              # Dashboard, file listing, download, delete, upload
│   ├── sync.py               # /sync/check, /sync/upload
│   └── admin.py              # User and API key management
├── utils/helpers.py          # SHA-256, token generation, path builders
├── static/style.css          # UI stylesheet
└── templates/                # Jinja2 templates
    ├── base.html
    ├── login.html
    ├── index.html
    ├── files.html
    ├── users.html
    └── api_keys.html

uploads/                      # Stored files (inside server/)
  seismic/YEAR/NET/STA/CHAN.TYPE/NET.STA.LOC.CHAN.TYPE.YEAR.DAY
  deformation/STATION/YEAR/FILENAME
  multigas/STATION/YEAR/FILENAME
  visual/STATION/YEAR/FILENAME
  weather/STATION/YEAR/FILENAME
```

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
deformation/STA1/2024/gps_daily.csv
multigas/STA3/2024/so2_flux.csv
visual/STA1/2024/cam01_2024001.jpg
weather/STA2/2024/met_2024001.csv
```

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
    "station": "STA1",
    "net": "VG",
    "loc": "",
    "chan": "EHZ",
    "sds_type": "D",
    "day": "001"
  },
  {
    "filename": "gps_daily.csv",
    "sha256": "b7c...",
    "data_type": "deformation",
    "station": "STA1"
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

| Field      | Required          | Description                              |
|------------|-------------------|------------------------------------------|
| `file`     | always            | File content                             |
| `data_type`| always            | `seismic` \| `deformation` \| `multigas` \| `visual` \| `weather` |
| `station`  | always            | Station identifier (maps to STA in SDS)  |
| `net`      | seismic only      | Network code                             |
| `loc`      | seismic only      | Location code (may be empty)             |
| `chan`     | seismic only      | Channel code, e.g. `EHZ`                |
| `sds_type` | seismic only      | SDS record type, e.g. `D`               |
| `day`      | seismic only      | Day of year, zero-padded, e.g. `001`    |

**Seismic example:**

```bash
curl -X POST http://localhost:8000/sync/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@VG.STA1..EHZ.D.2024.001" \
  -F "data_type=seismic" \
  -F "station=STA1" \
  -F "net=VG" \
  -F "loc=" \
  -F "chan=EHZ" \
  -F "sds_type=D" \
  -F "day=001"
```

**Non-seismic example:**

```bash
curl -X POST http://localhost:8000/sync/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@so2_flux.csv" \
  -F "data_type=multigas" \
  -F "station=STA3"
```

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

Download a file by its database ID (session auth required).

### `DELETE /files/{id}/delete`

Delete a file record and its data from disk. Admin only (POST form, session auth).

## Web Dashboard

| Route              | Access       | Description                        |
|--------------------|--------------|------------------------------------|
| `/`                | all roles    | Data group cards with file counts  |
| `/files/{type}`    | all roles    | File listing with station filter   |
| `/admin/users`     | admin        | Create, delete, change passwords   |
| `/admin/api-keys`  | admin        | Generate, revoke, delete API keys  |

## Authentication

**Dashboard** — form login at `/login`, session cookie (`lms_session`).

**API clients** — `Authorization: Bearer <token>` header. Tokens are generated by an admin in the dashboard or via `POST /admin/api-keys`. The raw token is shown once; the server stores only its SHA-256 hash.

Revoked keys are rejected immediately.

## License

MIT
