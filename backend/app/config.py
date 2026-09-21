from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "贴心小护士"
    debug: bool = True
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    database_url: str = "postgresql+asyncpg://nurse:nurse_secret@localhost:5432/nurse_assistant"
    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "nurse-reports"
    minio_secure: bool = False

    jwt_secret_key: str = "change-this-to-a-random-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_embedding_model: str = "text-embedding-3-small"

    # 是否启用 RAG 知识检索（调试记忆功能时可暂时关闭）
    enable_rag: bool = True

    # 讯飞开放平台语音（语音听写 ASR + 语音合成 TTS）
    iflytek_appid: str = ""
    iflytek_api_key: str = ""
    iflytek_api_secret: str = ""
    iflytek_tts_voice: str = "xiaoyan"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
