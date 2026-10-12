"""后端启动入口，同时保留 main:app 供 Uvicorn 使用。"""

from backend.app import app, main


if __name__ == "__main__":
    main()
