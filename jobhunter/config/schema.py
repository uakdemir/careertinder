
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid."""


class RemoteIoSearchProfile(BaseModel):
    """A single Remote.io search URL to scrape."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    label: str
    url: str
    max_pages: int = Field(default=5, ge=1, le=50)


class RemoteIoConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = True
    delay_seconds: int = 2
    search_profiles: list[RemoteIoSearchProfile] = Field(
        default_factory=lambda: [
            RemoteIoSearchProfile(label="Default", url="https://remote.io/remote-jobs", max_pages=10)
        ]
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: dict) -> dict:  # type: ignore[type-arg]
        if isinstance(data, dict) and "base_url" in data and "search_profiles" not in data:
            data["search_profiles"] = [{
                "label": "Default",
                "url": data.pop("base_url"),
                "max_pages": data.pop("max_pages", 10),
            }]
        return data


class RemoteRocketshipSearchProfile(BaseModel):
    """A single RemoteRocketship search URL to scrape."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    label: str
    url: str
    max_pages: int = Field(default=5, ge=1, le=50)


class RemoteRocketshipConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = True
    delay_seconds: int = 2
    search_profiles: list[RemoteRocketshipSearchProfile] = Field(
        default_factory=lambda: [
            RemoteRocketshipSearchProfile(
                label="Default", url="https://www.remoterocketship.com", max_pages=10
            )
        ]
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: dict) -> dict:  # type: ignore[type-arg]
        if isinstance(data, dict) and "base_url" in data and "search_profiles" not in data:
            data["search_profiles"] = [{
                "label": "Default",
                "url": data.pop("base_url"),
                "max_pages": data.pop("max_pages", 10),
            }]
        return data


class WellfoundSearchProfile(BaseModel):
    """A single Wellfound search query for Apify actor."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    label: str
    search_keyword: str
    location_filter: str = "remote"
    start_url: str | None = None
    source_url: str | None = None
    weight: int = Field(default=1, ge=1, le=10)


class WellfoundConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = False  # Deferred: all Apify actors require manual cookie/CAPTCHA
    apify_actor_id: str = "shahidirfan/wellfound-jobs-scraper"
    max_results: int = 100
    search_profiles: list[WellfoundSearchProfile] = Field(
        default_factory=lambda: [
            WellfoundSearchProfile(
                label="Default", search_keyword="software engineer", location_filter="remote"
            )
        ]
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: dict) -> dict:  # type: ignore[type-arg]
        if isinstance(data, dict) and "search_keyword" in data and "search_profiles" not in data:
            data["search_profiles"] = [{
                "label": "Default",
                "search_keyword": data.pop("search_keyword"),
                "location_filter": data.pop("location_filter", "remote"),
            }]
        return data


class LinkedInSearchProfile(BaseModel):
    """A structured LinkedIn search query for valig Apify actor.

    Supports all major LinkedIn job search filters including job functions
    and geographic targeting via LinkedIn's geoId system.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    label: str
    job_titles: list[str] = Field(default_factory=list)  # Keywords for title search
    locations: list[str] = Field(default_factory=list)  # Location strings (city, country)
    geo_id: str | None = None  # LinkedIn geoId (e.g., "102105699" for Turkey)
    workplace_type: list[str] = Field(default_factory=lambda: ["remote"])
    experience_level: list[str] = Field(default_factory=lambda: ["mid-senior", "director"])
    job_functions: list[str] = Field(default_factory=list)  # LinkedIn codes: it, eng, prjm, etc.
    contract_type: list[str] = Field(default_factory=list)  # Full-time, Part-time, Contract, etc.
    posted_limit: str | None = None  # 24h, week, month
    source_url: str | None = None  # Original LinkedIn search URL
    weight: int = Field(default=1, ge=1, le=10)


class LinkedInConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    enabled: bool = True
    apify_actor_id: str = "valig/linkedin-jobs-scraper"  # 3x cheaper than HarvestAPI
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
    """Nested model for location keyword lists."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    include: list[str] = Field(
        default_factory=lambda: [
            "remote",
            "remote-friendly",
            "fully remote",
            "worldwide",
            "anywhere",
            "global",
            "turkey",
            "europe",
            "emea",
        ]
    )
    exclude: list[str] = Field(
        default_factory=lambda: [
            "us only",
            "usa only",
            "united states only",
            "us-based only",
            "must be located in",
            "no remote",
            "on-site required",
        ]
    )


class FilteringConfig(BaseModel):
    """Pydantic model for Tier 1 filtering configuration.

    Stored in settings table as JSON. Dashboard edits are validated against this schema.
    Missing salary always results in AMBIGUOUS (not configurable per design philosophy).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    salary_min_usd: int = Field(default=90000, gt=0)
    location_keywords: LocationKeywordsConfig = Field(default_factory=LocationKeywordsConfig)
    title_whitelist: list[str] = Field(
        default_factory=lambda: [
            "architect",
            "principal",
            "staff",
            "lead",
            "senior",
            "director",
            "vp",
            "head of",
            "manager",
            "engineering manager",
            "tech lead",
            "team lead",
        ]
    )
    title_blacklist: list[str] = Field(
        default_factory=lambda: [
            "intern",
            "internship",
            "junior",
            "entry level",
            "entry-level",
            "associate",
            "co-op",
            "graduate",
            "trainee",
            "part-time",
        ]
    )
    company_whitelist: list[str] = Field(default_factory=list)
    company_blacklist: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(
        default_factory=lambda: [
            "python",
            "golang",
            "go",
            "rust",
            "distributed systems",
            "microservices",
            "cloud",
            "aws",
            "kubernetes",
            "k8s",
            "architecture",
            "system design",
        ]
    )
    excluded_keywords: list[str] = Field(
        default_factory=lambda: [
            "clearance required",
            "security clearance",
            "on-site only",
            "no remote",
            "must relocate",
            "relocation required",
            "visa sponsorship not available",
        ]
    )


class AICostConfig(BaseModel):
    """AI cost cap settings — stored in DB settings table (category 'ai_cost')."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    daily_cap_usd: float = Field(default=2.00, ge=0.0)
    warn_at_percent: float = Field(default=0.8, ge=0.0, le=1.0)


class AIModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    provider: str = "openai"
    model: str = "gpt-5-nano"
    max_tokens: int = 2000
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)


class AIModelsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    tier2: AIModelConfig = AIModelConfig()
    tier3: AIModelConfig = AIModelConfig(model="gpt-5.2", max_tokens=2000, temperature=0.3)
    content_gen: AIModelConfig = AIModelConfig(model="gpt-5.4", max_tokens=2000, temperature=0.5)


class DatabaseConfig(BaseModel):
    """Database configuration supporting SQLite and PostgreSQL.

    For SQLite: set driver="sqlite" and path="data/jobhunter.db"
    For PostgreSQL: set driver="postgresql" and host/port/name/user
                    (env vars DATABASE_HOST, DATABASE_PORT, DATABASE_NAME,
                     DATABASE_USER, DATABASE_PASSWORD override these values)
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    driver: str = "sqlite"  # "sqlite" or "postgresql"
    # SQLite settings
    path: str = "data/jobhunter.db"
    # PostgreSQL settings
    host: str = "localhost"
    port: int = 5432
    name: str = "jobhunter"
    user: str = "jobhunter"
    # Common settings
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
    # PostgreSQL connection (env vars override config.yaml values)
    database_host: str | None = None
    database_port: int | None = None
    database_name: str | None = None
    database_user: str | None = None
    database_password: str | None = None
