from fastapi import FastAPI

app = FastAPI(title="Room Fit")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
