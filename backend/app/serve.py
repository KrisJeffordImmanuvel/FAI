"""Production entry point (used by the Docker image / cloud hosting).

* seeds the demo database on first start (an empty disk → fresh demo data),
* listens on 0.0.0.0 and the port given by the host in ``$PORT`` (Render, Railway,
  Hugging Face Spaces and most platforms set it),
* prints the agent's decisions to the platform's log stream.
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    os.environ.setdefault("LIBRARY_CONSOLE_LOG", "1")
    from .seed import ensure_seeded

    if ensure_seeded():
        print("Seeded a fresh demo database.", flush=True)
    port = int(os.environ.get("PORT", "8000"))
    print(f"Serving the library agent on 0.0.0.0:{port}", flush=True)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,  # correct client IPs/scheme behind the host's HTTPS proxy
        forwarded_allow_ips="*",
        access_log=os.environ.get("LIBRARY_ACCESS_LOG") == "1",
    )


if __name__ == "__main__":
    main()
