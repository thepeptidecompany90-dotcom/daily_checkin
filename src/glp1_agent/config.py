from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    openai_api_key: str = ""
    daily_api_key: str = ""
    bot_base_url: str = "http://127.0.0.1:7860"
