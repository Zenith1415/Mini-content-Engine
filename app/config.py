from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    POSTGRES_USER: str = "glitr"
    POSTGRES_PASSWORD: str = "glitr"
    POSTGRES_DB: str = "glitr"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    GEMINI_API_KEY: str = ""
    IMAGE_PROVIDER: str = "mock"
    STORAGE_DIR: str = "./storage"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    DEBUG: bool = False

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()