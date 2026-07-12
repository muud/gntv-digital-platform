# CMS Module 3 — Premium Streaming Catalog API

Base path: `/api/v1/catalog`. Bearer JWT authentication is required. Catalog reads use the existing `content:read` CMS scope; catalog mutations use `content:write`. Consumer-specific progress, ratings, and recommendations require an authenticated user.

## Catalog types

`movie`, `series`, `season`, `episode`, `live_tv`, `radio`, `podcast`, `short`, `kids`, and `news`. A season must belong to a series; an episode must belong to a season. Module 3 stores source/stream references only and performs no transcoding.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/items` | Create any catalog title/channel/program |
| GET | `/items` | Search, filter, and paginate |
| GET/PATCH/DELETE | `/items/{id}` | Detail, update, soft delete |
| POST | `/items/{id}/restore` | Restore deleted item |
| POST | `/taxonomies/{genre\|language\|region}` | Create localized taxonomy |
| POST | `/people` | Create cast/crew person |
| POST | `/studios` | Create studio/producer organization |
| POST | `/collections` | Create collection or featured row |
| GET | `/featured-rows` | Ordered premium home-screen rows |
| PUT | `/items/{id}/progress` | Update continue-watching progress |
| GET | `/continue-watching` | Current user's unfinished titles |
| PUT | `/items/{id}/rating` | Set 0–5 rating |
| GET | `/recommendations` | Genre-affinity recommendations |
| POST | `/items/{id}/ai-hooks` | Queue classify, summarize, tag, SEO, or recommendation enrichment |

List filters: `search`, `catalog_type`, `status`, `genre_id`, `language_id`, `region_id`, `is_kids`, `limit`, and `offset`.

## Metadata

Every item includes premium/kids flags, age rating, hierarchy, runtime, release date, studio, media/poster asset UUIDs, SEO title/description/keywords, extensible metadata JSON, and AI metadata/status. Credits distinguish cast, crew, directors, and producers and allow character names and display ordering.

AI hooks use a dispatch protocol. The default implementation only records the queued state; no external AI or transcoding engine is invoked by Module 3.
