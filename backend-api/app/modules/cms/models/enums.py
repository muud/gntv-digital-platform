"""CMS enum definitions from the approved database specification."""

from enum import StrEnum


class ContentType(StrEnum):
    LIVE_TV = "live_tv"
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    SEASON = "season"
    EPISODE = "episode"
    PODCAST = "podcast"
    RADIO = "radio"
    ARTICLE = "article"
    BREAKING_NEWS = "breaking_news"
    SHORT = "short"
    KIDS = "kids"
    EDUCATION = "education"
    COMMUNITY_POST = "community_post"


class WorkflowState(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    FACT_CHECK = "fact_check"
    EDITORIAL_APPROVAL = "editorial_approval"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    FACT_CHECK = "fact_check"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"
    MEMBERS = "members"
