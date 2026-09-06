"""Run `python -m pauth` to start the local API with reload on 127.0.0.1:8000."""

from pauth.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("pauth.main:app", host="127.0.0.1", port=8000, reload=True)
