from fastapi import FastAPI

app = FastAPI(
    title="Mockina API",
    description="Backend for the Mockina AI mock-interview platform.",
    version="0.1.0",
)


@app.get("/", summary="Check API Health", response_description="API is running properly.")
def health():
    """
    Reports that the API is running.

    Takes no input and does no work, so a client can call it to check
    that the server is reachable.
    """
    return {"status": "healthy"}
