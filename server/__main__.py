import uvicorn

from server.config import DEBUG, SERVER_HOST, SERVER_PORT


def main():
    uvicorn.run(
        "server.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=DEBUG,
    )


if __name__ == "__main__":
    main()
