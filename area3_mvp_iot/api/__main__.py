"""Sobe a API: python -m area3_mvp_iot.api"""
import uvicorn

from comum.config import env


def main() -> None:
    uvicorn.run(
        "area3_mvp_iot.api.app:criar_app",
        factory=True,
        host=env("MARGEM_HOST", "127.0.0.1"),
        port=int(env("MARGEM_PORTA", "8080")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
