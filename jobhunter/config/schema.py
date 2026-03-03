
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid."""


class RemoteIoConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = True
    base_url: str = "https://remote.io/remote-jobs"
    max_pages: int = 10
    delay_seconds: int = 2


class RemoteRocketshipConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = True
    base_url: str = "https://www.remoterocketship.com"
    max_pages: int = 10
    delay_seconds: int = 2


class WellfoundConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = False  # Deferred: all Apify actors require manual cookie/CAPTCHA
    apify_actor_id: str = "shahidirfan/wellfound-jobs-scraper"
    max_results: int = 100
    search_keyword: str = "software engineer"
    location_filter: str = "remote"


class LinkedInSearchProfile(BaseModel):
    """A structured LinkedIn search query for the HarvestAPI actor."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    label: str
    job_titles: list[str]
    locations: list[str] = []
    workplace_type: list[str] = Field(default_factory=lambda: ["remote"])
    experience_level: list[str] = Field(default_factory=lambda: ["mid-senior", "director"])
    salary: str | None = None
    posted_limit: str | None = None
    weight: int = Field(default=1, ge=1, le=10)


class LinkedInConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = True
    apify_actor_id: str = "harvestapi/linkedin-job-search"
    max_results: int = 100
    search_profiles: list[LinkedInSearchProfile] = Field(default_factory=list)


class ScrapingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    remote_io: RemoteIoConfig = RemoteIoConfig()
    remote_rocketship: RemoteRocketshipConfig = RemoteRocketshipConfig()
    wellfound: WellfoundConfig = WellfoundConfig()
    linkedin: LinkedInConfig = LinkedInConfig()
    timeout_seconds: int = 600


class LocationKeywordsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    include: list[str] = ["remote", "worldwide", "anywhere", "turkey", "europe", "emea"]
    exclude: list[str] = ["us only", "us-based only", "must be in us"]


class FilteringConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    salary_min_usd: int = Field(default=90000, gt=0)
    location_keywords: LocationKeywordsConfig = LocationKeywordsConfig()
    title_whitelist: list[str] = ["architect", "principal", "staff", "lead", "director", "vp", "head of", "manager"]
    title_blacklist: list[str] = ["intern", "junior", "entry level"]
    company_blacklist: list[str] = []


class AIModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    provider: str = "anthropic"
    model: str = "claude-3-5-haiku-latest"
    max_tokens: int = 300
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)


class AIModelsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    tier2: AIModelConfig = AIModelConfig()
    tier3: AIModelConfig = AIModelConfig(model="claude-sonnet-4-20250514", max_tokens=2000, temperature=0.3)
    content_gen: AIModelConfig = AIModelConfig(provider="openai", model="gpt-4o", max_tokens=2000, temperature=0.5)


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    path: str = "data/jobhunter.db"
    echo_sql: bool = False


class DashboardConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    port: int = 8501
    page_size: int = 25


class SchedulingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    run_interval_hours: int = 12
    retry_failed_scrapers: bool = True
    max_retries: int = 2


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = False
    method: str = "email"
    min_score_to_notify: int = 80


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    scraping: ScrapingConfig = ScrapingConfig()
    filtering: FilteringConfig = FilteringConfig()
    ai_models: AIModelsConfig = AIModelsConfig()
    database: DatabaseConfig = DatabaseConfig()
    dashboard: DashboardConfig = DashboardConfig()
    scheduling: SchedulingConfig = SchedulingConfig()
    notifications: NotificationsConfig = NotificationsConfig()


class SecretsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    apify_api_token: str | None = None
