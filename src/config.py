from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str

    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "deepseek/deepseek-v4-flash"

    data_dir: str = "./data"

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8080/oauth/callback"

    max_memories_per_query: int = 5
    profile_update_threshold: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
