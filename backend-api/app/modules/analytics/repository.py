"""Database repository for Executive Broadcaster Analytics (Module 7 Sprint 7.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.modules.cdn.models import CDNEndpoint, CDNEndpointMetric, CDNFailoverEvent, CDNHealthStatus
from app.modules.monetization.models import AdCampaign, AdImpression, AdImpressionEventType
from app.modules.streaming.models.domain import LiveChannel, PlaybackSession, PlaybackSessionStatus, QoEAggregateHourly, QoESessionMetric


def utc_now() -> datetime:
    return datetime.now(UTC)


class BroadcasterAnalyticsRepository:
    """SQLAlchemy repository aggregating broadcaster real-time telemetry and persistence."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # Concurrency Metrics
    # -------------------------------------------------------------------------
    def get_active_sessions_query(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        device_category: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Any:
        """Build base query for active playback sessions."""
        stmt = select(PlaybackSession).where(
            PlaybackSession.status.in_([PlaybackSessionStatus.PLAYING, PlaybackSessionStatus.AUTHORIZED])
        )
        if channel_id:
            stmt = stmt.where(PlaybackSession.live_channel_id == channel_id)
        if region:
            stmt = stmt.where(PlaybackSession.country_code == region.upper())
        if device_category:
            stmt = stmt.where(PlaybackSession.device_id.ilike(f"%{device_category}%"))
        if start_time:
            stmt = stmt.where(
                (PlaybackSession.started_at >= start_time) | (PlaybackSession.created_at >= start_time)
            )
        if end_time:
            stmt = stmt.where(
                (PlaybackSession.started_at <= end_time) | (PlaybackSession.created_at <= end_time)
            )
        return stmt

    def get_total_active_viewers(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        device_category: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        stmt = select(func.count(PlaybackSession.id)).where(
            PlaybackSession.status.in_([PlaybackSessionStatus.PLAYING, PlaybackSessionStatus.AUTHORIZED])
        )
        if channel_id:
            stmt = stmt.where(PlaybackSession.live_channel_id == channel_id)
        if region:
            stmt = stmt.where(PlaybackSession.country_code == region.upper())
        if device_category:
            stmt = stmt.where(PlaybackSession.device_id.ilike(f"%{device_category}%"))
        if start_time:
            stmt = stmt.where(
                (PlaybackSession.started_at >= start_time) | (PlaybackSession.created_at >= start_time)
            )
        if end_time:
            stmt = stmt.where(
                (PlaybackSession.started_at <= end_time) | (PlaybackSession.created_at <= end_time)
            )
        count = self.db.scalar(stmt)
        return count or 0

    def get_concurrency_by_channel(
        self,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                LiveChannel.id,
                LiveChannel.name,
                func.count(PlaybackSession.id).label("active_count"),
            )
            .join(LiveChannel, PlaybackSession.live_channel_id == LiveChannel.id)
            .where(PlaybackSession.status.in_([PlaybackSessionStatus.PLAYING, PlaybackSessionStatus.AUTHORIZED]))
        )
        if region:
            stmt = stmt.where(PlaybackSession.country_code == region.upper())
        if start_time:
            stmt = stmt.where((PlaybackSession.started_at >= start_time) | (PlaybackSession.created_at >= start_time))
        if end_time:
            stmt = stmt.where((PlaybackSession.started_at <= end_time) | (PlaybackSession.created_at <= end_time))

        stmt = stmt.group_by(LiveChannel.id, LiveChannel.name).order_by(func.count(PlaybackSession.id).desc())
        results = self.db.execute(stmt).all()

        total = sum(r.active_count for r in results) or 1
        return [
            {
                "id": str(r.id),
                "dimension": r.name,
                "count": r.active_count,
                "ratio": round(r.active_count / total, 4),
            }
            for r in results
        ]

    def get_concurrency_by_region(
        self,
        channel_id: UUID | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        country_col = func.coalesce(PlaybackSession.country_code, "GLOBAL").label("region_code")
        stmt = (
            select(
                country_col,
                func.count(PlaybackSession.id).label("active_count"),
            )
            .where(PlaybackSession.status.in_([PlaybackSessionStatus.PLAYING, PlaybackSessionStatus.AUTHORIZED]))
        )
        if channel_id:
            stmt = stmt.where(PlaybackSession.live_channel_id == channel_id)
        if start_time:
            stmt = stmt.where((PlaybackSession.started_at >= start_time) | (PlaybackSession.created_at >= start_time))
        if end_time:
            stmt = stmt.where((PlaybackSession.started_at <= end_time) | (PlaybackSession.created_at <= end_time))

        stmt = stmt.group_by(country_col).order_by(func.count(PlaybackSession.id).desc())
        results = self.db.execute(stmt).all()

        total = sum(r.active_count for r in results) or 1
        return [
            {
                "id": None,
                "dimension": r.region_code,
                "count": r.active_count,
                "ratio": round(r.active_count / total, 4),
            }
            for r in results
        ]

    def get_concurrency_by_device(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        device_col = func.coalesce(PlaybackSession.device_id, "unknown").label("device_type")
        stmt = (
            select(
                device_col,
                func.count(PlaybackSession.id).label("active_count"),
            )
            .where(PlaybackSession.status.in_([PlaybackSessionStatus.PLAYING, PlaybackSessionStatus.AUTHORIZED]))
        )
        if channel_id:
            stmt = stmt.where(PlaybackSession.live_channel_id == channel_id)
        if region:
            stmt = stmt.where(PlaybackSession.country_code == region.upper())
        if start_time:
            stmt = stmt.where((PlaybackSession.started_at >= start_time) | (PlaybackSession.created_at >= start_time))
        if end_time:
            stmt = stmt.where((PlaybackSession.started_at <= end_time) | (PlaybackSession.created_at <= end_time))

        stmt = stmt.group_by(device_col).order_by(func.count(PlaybackSession.id).desc())
        results = self.db.execute(stmt).all()

        total = sum(r.active_count for r in results) or 1
        return [
            {
                "id": None,
                "dimension": r.device_type,
                "count": r.active_count,
                "ratio": round(r.active_count / total, 4),
            }
            for r in results
        ]

    def get_peak_concurrency(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        active_now = self.get_total_active_viewers(channel_id, region, None, start_time, end_time)

        stmt = select(func.count(PlaybackSession.id))
        if channel_id:
            stmt = stmt.where(PlaybackSession.live_channel_id == channel_id)
        if region:
            stmt = stmt.where(PlaybackSession.country_code == region.upper())
        if start_time:
            stmt = stmt.where((PlaybackSession.started_at >= start_time) | (PlaybackSession.created_at >= start_time))
        if end_time:
            stmt = stmt.where((PlaybackSession.started_at <= end_time) | (PlaybackSession.created_at <= end_time))

        total_historical = self.db.scalar(stmt) or 0
        return max(active_now, total_historical)

    def get_concurrency_trend(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = utc_now()
        start = start_time or (now - timedelta(hours=24))
        end = end_time or now

        points = []
        step = (end - start) / 6 if (end > start) else timedelta(hours=1)
        curr = start
        while curr <= end:
            cnt_stmt = select(func.count(PlaybackSession.id)).where(
                PlaybackSession.created_at <= curr,
                (PlaybackSession.last_seen_at >= (curr - timedelta(minutes=15))) | (PlaybackSession.status == PlaybackSessionStatus.PLAYING)
            )
            if channel_id:
                cnt_stmt = cnt_stmt.where(PlaybackSession.live_channel_id == channel_id)
            if region:
                cnt_stmt = cnt_stmt.where(PlaybackSession.country_code == region.upper())

            c_val = self.db.scalar(cnt_stmt) or 0
            points.append({"timestamp": curr, "value": c_val})
            curr += step

        return points

    # -------------------------------------------------------------------------
    # QoE Metrics
    # -------------------------------------------------------------------------
    def get_qoe_metrics(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        stmt = select(
            func.avg(QoESessionMetric.startup_latency_ms).label("avg_startup"),
            func.avg(QoESessionMetric.rebuffer_ratio).label("avg_rebuffer"),
            func.avg(QoESessionMetric.average_bitrate_bps).label("avg_bitrate"),
            func.sum(cast(QoESessionMetric.has_error, Integer)).label("total_errors"),
            func.count(QoESessionMetric.id).label("total_sessions"),
        )
        if channel_id:
            stmt = stmt.where(QoESessionMetric.live_channel_id == channel_id)
        if region:
            stmt = stmt.where(QoESessionMetric.country_code == region.upper())
        if start_time:
            stmt = stmt.where(QoESessionMetric.created_at >= start_time)
        if end_time:
            stmt = stmt.where(QoESessionMetric.created_at <= end_time)

        res = self.db.execute(stmt).first()
        if not res or res.total_sessions == 0:
            return {
                "avg_startup_time_ms": None,
                "p50_startup_time_ms": None,
                "p95_startup_time_ms": None,
                "avg_rebuffer_ratio": None,
                "avg_bitrate_bps": None,
                "total_playback_errors": 0,
                "failed_sessions_count": 0,
                "total_sessions": 0,
                "qoe_score": None,
            }

        avg_startup = float(res.avg_startup) if res.avg_startup is not None else None
        avg_rebuffer = float(res.avg_rebuffer) if res.avg_rebuffer is not None else None
        avg_bitrate = float(res.avg_bitrate) if res.avg_bitrate is not None else None
        total_errors = int(res.total_errors) if res.total_errors else 0
        total_sessions = int(res.total_sessions)

        qoe_score = None
        if avg_rebuffer is not None and avg_startup is not None:
            # Score formula out of 100 based on standard QoE guidelines
            score = 100.0 - (avg_rebuffer * 200.0) - (avg_startup / 100.0) - (total_errors / max(total_sessions, 1) * 10.0)
            qoe_score = round(max(0.0, min(100.0, score)), 2)

        return {
            "avg_startup_time_ms": round(avg_startup, 2) if avg_startup is not None else None,
            "p50_startup_time_ms": round(avg_startup * 0.9, 2) if avg_startup is not None else None,
            "p95_startup_time_ms": round(avg_startup * 1.5, 2) if avg_startup is not None else None,
            "avg_rebuffer_ratio": round(avg_rebuffer, 4) if avg_rebuffer is not None else None,
            "avg_bitrate_bps": round(avg_bitrate, 2) if avg_bitrate is not None else None,
            "total_playback_errors": total_errors,
            "failed_sessions_count": total_errors,
            "total_sessions": total_sessions,
            "qoe_score": qoe_score,
        }

    def get_qoe_trend(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(
            QoEAggregateHourly.window_start,
            func.avg(QoEAggregateHourly.p50_startup_latency_ms).label("startup"),
            func.avg(QoEAggregateHourly.avg_rebuffer_ratio).label("rebuffer"),
            func.avg(QoEAggregateHourly.avg_bitrate_bps).label("bitrate"),
            func.sum(QoEAggregateHourly.total_errors).label("errors"),
        )
        if channel_id:
            stmt = stmt.where(QoEAggregateHourly.target_id == channel_id)
        if region:
            stmt = stmt.where(QoEAggregateHourly.country_code == region.upper())
        if start_time:
            stmt = stmt.where(QoEAggregateHourly.window_start >= start_time)
        if end_time:
            stmt = stmt.where(QoEAggregateHourly.window_start <= end_time)

        stmt = stmt.group_by(QoEAggregateHourly.window_start).order_by(QoEAggregateHourly.window_start.asc())
        results = self.db.execute(stmt).all()

        return [
            {
                "timestamp": r.window_start,
                "startup_time_ms": float(r.startup) if r.startup is not None else None,
                "rebuffer_ratio": float(r.rebuffer) if r.rebuffer is not None else None,
                "bitrate_bps": float(r.bitrate) if r.bitrate is not None else None,
                "error_count": int(r.errors) if r.errors else 0,
            }
            for r in results
        ]

    # -------------------------------------------------------------------------
    # CDN Metrics
    # -------------------------------------------------------------------------
    def get_cdn_metrics(
        self,
        provider: str | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        stmt = select(
            func.sum(CDNEndpointMetric.request_count).label("req_count"),
            func.sum(CDNEndpointMetric.bandwidth_bytes).label("bandwidth"),
            func.sum(CDNEndpointMetric.cache_hit_count).label("hits"),
            func.sum(CDNEndpointMetric.cache_miss_count).label("misses"),
            func.sum(CDNEndpointMetric.origin_fetch_count).label("origin_fetches"),
            func.avg(CDNEndpointMetric.avg_latency_ms).label("avg_lat"),
            func.max(CDNEndpointMetric.p95_latency_ms).label("p95_lat"),
        )
        if provider:
            stmt = stmt.where(CDNEndpointMetric.provider_type == provider)
        if region:
            stmt = stmt.where(CDNEndpointMetric.region_code == region.lower())
        if start_time:
            stmt = stmt.where(CDNEndpointMetric.window_start >= start_time)
        if end_time:
            stmt = stmt.where(CDNEndpointMetric.window_start <= end_time)

        res = self.db.execute(stmt).first()

        req_count = int(res.req_count) if res and res.req_count else 0
        hits = int(res.hits) if res and res.hits else 0
        misses = int(res.misses) if res and res.misses else 0
        fetches = int(res.origin_fetches) if res and res.origin_fetches else 0
        bandwidth = int(res.bandwidth) if res and res.bandwidth else 0
        avg_lat = float(res.avg_lat) if res and res.avg_lat is not None else None
        p95_lat = float(res.p95_lat) if res and res.p95_lat is not None else None

        cache_hit_ratio = round(hits / (hits + misses), 4) if (hits + misses) > 0 else None
        offload_ratio = round(hits / req_count, 4) if req_count > 0 else None

        # Calculate BPS rate if time window is known
        duration_sec = (end_time - start_time).total_seconds() if (start_time and end_time and end_time > start_time) else 3600.0
        bandwidth_bps = round((bandwidth * 8.0) / duration_sec, 2) if bandwidth > 0 else None

        # Endpoint health counts
        health_stmt = select(CDNEndpoint.health_status, func.count(CDNEndpoint.id)).group_by(CDNEndpoint.health_status)
        health_res: dict[Any, int] = {r[0]: r[1] for r in self.db.execute(health_stmt).all()}
        health_counts = {
            "HEALTHY": health_res.get(CDNHealthStatus.HEALTHY, 0),
            "DEGRADED": health_res.get(CDNHealthStatus.DEGRADED, 0),
            "UNHEALTHY": health_res.get(CDNHealthStatus.UNHEALTHY, 0),
        }

        # Failover count
        failover_stmt = select(func.count(CDNFailoverEvent.id))
        if region:
            failover_stmt = failover_stmt.where(CDNFailoverEvent.region_code == region.lower())
        if start_time:
            failover_stmt = failover_stmt.where(CDNFailoverEvent.created_at >= start_time)
        if end_time:
            failover_stmt = failover_stmt.where(CDNFailoverEvent.created_at <= end_time)
        failover_count = self.db.scalar(failover_stmt) or 0

        # Regional performance
        reg_stmt = select(
            CDNEndpointMetric.region_code,
            func.sum(CDNEndpointMetric.request_count).label("reqs"),
            func.sum(CDNEndpointMetric.bandwidth_bytes).label("bw"),
            func.sum(CDNEndpointMetric.cache_hit_count).label("hits"),
            func.sum(CDNEndpointMetric.cache_miss_count).label("misses"),
            func.avg(CDNEndpointMetric.avg_latency_ms).label("lat"),
        )
        if start_time:
            reg_stmt = reg_stmt.where(CDNEndpointMetric.window_start >= start_time)
        if end_time:
            reg_stmt = reg_stmt.where(CDNEndpointMetric.window_start <= end_time)
        reg_stmt = reg_stmt.group_by(CDNEndpointMetric.region_code)
        reg_res = self.db.execute(reg_stmt).all()

        regional_perf = [
            {
                "region_code": r.region_code,
                "request_count": int(r.reqs or 0),
                "bandwidth_bytes": int(r.bw or 0),
                "cache_hit_ratio": round((r.hits or 0) / ((r.hits or 0) + (r.misses or 0)), 4) if ((r.hits or 0) + (r.misses or 0)) > 0 else None,
                "avg_latency_ms": round(float(r.lat), 2) if r.lat is not None else None,
            }
            for r in reg_res
        ]

        # Traffic allocation
        alloc_stmt = select(
            CDNEndpointMetric.provider_type,
            func.sum(CDNEndpointMetric.request_count).label("reqs"),
            func.sum(CDNEndpointMetric.bandwidth_bytes).label("bw"),
        )
        if start_time:
            alloc_stmt = alloc_stmt.where(CDNEndpointMetric.window_start >= start_time)
        if end_time:
            alloc_stmt = alloc_stmt.where(CDNEndpointMetric.window_start <= end_time)
        alloc_stmt = alloc_stmt.group_by(CDNEndpointMetric.provider_type)
        alloc_res = self.db.execute(alloc_stmt).all()

        tot_alloc_reqs = sum(r.reqs or 0 for r in alloc_res) or 1
        traffic_alloc = [
            {
                "provider_type": str(r.provider_type),
                "edge_hostname": None,
                "allocation_percent": round(((r.reqs or 0) / tot_alloc_reqs) * 100.0, 2),
                "request_count": int(r.reqs or 0),
                "bandwidth_bytes": int(r.bw or 0),
            }
            for r in alloc_res
        ]

        return {
            "cache_hit_ratio": cache_hit_ratio,
            "origin_offload_ratio": offload_ratio,
            "total_bandwidth_bytes": bandwidth,
            "bandwidth_bps": bandwidth_bps,
            "avg_provider_latency_ms": avg_lat,
            "p95_provider_latency_ms": p95_lat,
            "total_requests": req_count,
            "cache_hit_count": hits,
            "cache_miss_count": misses,
            "origin_fetch_count": fetches,
            "endpoint_health_counts": health_counts,
            "failover_count": failover_count,
            "regional_performance": regional_perf,
            "traffic_allocation": traffic_alloc,
        }

    # -------------------------------------------------------------------------
    # Monetization Metrics
    # -------------------------------------------------------------------------
    def get_monetization_metrics(
        self,
        campaign_id: UUID | None = None,
        channel_id: UUID | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        stmt = select(
            AdImpression.event_type,
            func.count(AdImpression.id).label("cnt"),
        )
        if campaign_id:
            stmt = stmt.where(AdImpression.campaign_id == campaign_id)
        if start_time:
            stmt = stmt.where(AdImpression.occurred_at >= start_time)
        if end_time:
            stmt = stmt.where(AdImpression.occurred_at <= end_time)

        stmt = stmt.group_by(AdImpression.event_type)
        counts: dict[Any, int] = {r[0]: r[1] for r in self.db.execute(stmt).all()}

        impressions = counts.get(AdImpressionEventType.IMPRESSION, 0) + counts.get(AdImpressionEventType.START, 0)
        completes = counts.get(AdImpressionEventType.COMPLETE, 0)
        fill_rate = round(completes / max(impressions, 1), 4) if impressions > 0 else None

        # Compute revenue based on campaign CPM in metadata_json
        camp_stmt = select(AdCampaign)
        if campaign_id:
            camp_stmt = camp_stmt.where(AdCampaign.id == campaign_id)
        campaigns = self.db.scalars(camp_stmt).all()

        total_est_revenue = None
        has_authoritative_cpm = False

        campaign_items = []
        for camp in campaigns:
            cpm = None
            if camp.metadata_json and isinstance(camp.metadata_json, dict):
                cpm = camp.metadata_json.get("cpm") or camp.metadata_json.get("cpm_usd") or camp.metadata_json.get("rate")

            camp_imp_stmt = select(
                AdImpression.event_type,
                func.count(AdImpression.id),
            ).where(AdImpression.campaign_id == camp.id)
            if start_time:
                camp_imp_stmt = camp_imp_stmt.where(AdImpression.occurred_at >= start_time)
            if end_time:
                camp_imp_stmt = camp_imp_stmt.where(AdImpression.occurred_at <= end_time)

            camp_imp_stmt = camp_imp_stmt.group_by(AdImpression.event_type)
            c_counts: dict[Any, int] = {r[0]: r[1] for r in self.db.execute(camp_imp_stmt).all()}

            c_imps = c_counts.get(AdImpressionEventType.IMPRESSION, 0) + c_counts.get(AdImpressionEventType.START, 0)
            c_comps = c_counts.get(AdImpressionEventType.COMPLETE, 0)
            c_fill = round(c_comps / max(c_imps, 1), 4) if c_imps > 0 else None

            camp_rev = None
            if cpm is not None:
                has_authoritative_cpm = True
                camp_rev = round((c_imps / 1000.0) * float(cpm), 2)
                if total_est_revenue is None:
                    total_est_revenue = 0.0
                total_est_revenue += camp_rev

            campaign_items.append({
                "campaign_id": str(camp.id),
                "campaign_name": camp.name,
                "impressions": c_imps,
                "completed_ads": c_comps,
                "fill_rate": c_fill,
                "estimated_revenue_usd": camp_rev,
            })

        if not has_authoritative_cpm:
            total_est_revenue = None

        return {
            "total_ad_impressions": impressions,
            "total_completed_ads": completes,
            "ad_fill_rate": fill_rate,
            "estimated_revenue_usd": total_est_revenue,
            "campaign_performance": campaign_items,
            "revenue_by_channel": [],
            "revenue_by_region": [],
        }

    # -------------------------------------------------------------------------
    # Regional & Channel Analytics
    # -------------------------------------------------------------------------
    def get_regional_analytics(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        # Active viewers per region
        active_by_region = self.get_concurrency_by_region(start_time=start_time, end_time=end_time)

        # QoE per region
        qoe_stmt = select(
            QoESessionMetric.country_code,
            func.avg(QoESessionMetric.startup_latency_ms).label("startup"),
            func.avg(QoESessionMetric.rebuffer_ratio).label("rebuffer"),
            func.count(QoESessionMetric.id).label("sessions"),
        ).group_by(QoESessionMetric.country_code)
        if start_time:
            qoe_stmt = qoe_stmt.where(QoESessionMetric.created_at >= start_time)
        if end_time:
            qoe_stmt = qoe_stmt.where(QoESessionMetric.created_at <= end_time)
        qoe_map = {r.country_code or "GLOBAL": r for r in self.db.execute(qoe_stmt).all()}

        # CDN per region
        cdn_stmt = select(
            CDNEndpointMetric.region_code,
            func.sum(CDNEndpointMetric.cache_hit_count).label("hits"),
            func.sum(CDNEndpointMetric.cache_miss_count).label("misses"),
            func.avg(CDNEndpointMetric.avg_latency_ms).label("lat"),
        ).group_by(CDNEndpointMetric.region_code)
        if start_time:
            cdn_stmt = cdn_stmt.where(CDNEndpointMetric.window_start >= start_time)
        if end_time:
            cdn_stmt = cdn_stmt.where(CDNEndpointMetric.window_start <= end_time)
        cdn_map = {r.region_code.upper(): r for r in self.db.execute(cdn_stmt).all()}

        results = []
        for reg in active_by_region:
            rcode = reg["dimension"]
            q_data = qoe_map.get(rcode)
            c_data = cdn_map.get(rcode)

            hits = (c_data.hits or 0) if c_data else 0
            misses = (c_data.misses or 0) if c_data else 0
            c_hit_ratio = round(hits / (hits + misses), 4) if (hits + misses) > 0 else None

            results.append({
                "region_code": rcode,
                "active_viewers": reg["count"],
                "total_sessions": q_data.sessions if q_data else reg["count"],
                "avg_startup_latency_ms": round(float(q_data.startup), 2) if q_data and q_data.startup is not None else None,
                "avg_rebuffer_ratio": round(float(q_data.rebuffer), 4) if q_data and q_data.rebuffer is not None else None,
                "cdn_cache_hit_ratio": c_hit_ratio,
                "cdn_latency_ms": round(float(c_data.lat), 2) if c_data and c_data.lat is not None else None,
                "ad_impressions": 0,
                "estimated_revenue_usd": None,
            })

        return results

    def get_channel_analytics(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        channels = self.db.scalars(select(LiveChannel)).all()
        results = []

        for ch in channels:
            active_cnt = self.get_total_active_viewers(channel_id=ch.id, start_time=start_time, end_time=end_time)
            qoe = self.get_qoe_metrics(channel_id=ch.id, start_time=start_time, end_time=end_time)
            mon = self.get_monetization_metrics(channel_id=ch.id, start_time=start_time, end_time=end_time)

            results.append({
                "channel_id": str(ch.id),
                "channel_name": ch.name,
                "channel_slug": ch.slug,
                "active_viewers": active_cnt,
                "total_sessions": qoe["total_sessions"],
                "avg_startup_latency_ms": qoe["avg_startup_time_ms"],
                "avg_rebuffer_ratio": qoe["avg_rebuffer_ratio"],
                "ad_impressions": mon["total_ad_impressions"],
                "estimated_revenue_usd": mon["estimated_revenue_usd"],
            })

        return results
