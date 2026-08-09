# GNTV DIGITAL — Playback Platform Risk Register (Module 6)

**Role**: Architecture and Release Director  
**Last Updated**: July 31, 2026

---

## 1. Risk Matrix Overview

The following risk register tracks technical, operational, and deployment risks identified for the Module 6 Playback Platform implementation.

| Risk ID | Description | Likelihood | Impact | Severity | Mitigation Strategy |
|---|---|---|---|---|---|
| **R-601** | **DRM License Retrieval Latency**<br>Slow responses from Alibaba KMS during license acquisition delay playback startup. | Medium | High | **High** | Implement pre-fetching of licenses during catalog load and keep KMS keys warm. Cache transient license routes in Redis. |
| **R-602** | **Concurrency Check Race Condition**<br>Simultaneous play requests evade ZSET check count, bypassing stream limit. | High | Medium | **Medium** | Enforce Redis checks using a Lua transaction script to guarantee atomicity. Evict oldest sessions retrospectively on heartbeat. |
| **R-603** | **Geo-Bypass via VPN/Proxy**<br>Users leverage commercial VPNs to view restricted broadcasts. | High | High | **High** | Integrate commercial VPN/Proxy IP blocklists into the Playback Authorization endpoint. Fail-closed on IP resolution failure. |
| **R-604** | **Watermarking Performance Overhead**<br>Forensic A/B segment CDN switching increases edge server cache miss rates. | Medium | Medium | **Medium** | Optimize CDN cache routing rules and pre-generate both A and B chunks in parallel during ingestion. |
| **R-605** | **Smart TV Key Focus Traps**<br>D-pad keyboard events trap navigation focus on custom overlay panels. | Medium | High | **High** | Implement strict focus boundary traps in JS. Perform regression testing on real Smart TV physical hardware (Tizen/webOS). |
| **R-606** | **Alibaba Cloud integration failure**<br>API credentials or RAM roles drift, blocking OSS manifest access. | Low | Critical | **High** | Use automated Terraform scripts to provision Access Keys. Run containerized integration health checks on startup. |
| **R-607** | **Warning Gate Deprecation Noise**<br>The 912 python deprecation warnings mask critical new warnings. | High | Low | **Low** | Configure `warnings.simplefilter("ignore")` selectively for known libraries, while raising errors on new deprecations. |

---

## 2. Risk Response & Monitoring Plans

### R-602: Concurrency Race Condition Detail
- **Trigger**: Single subscriber uses script to request 10 signed play tokens within 100 milliseconds.
- **Monitoring**: Datadog/Sentry logs tracking `session_eviction_events` per user. High eviction rates flags account for security review.

### R-603: Geo-Bypass Detail
- **Trigger**: Regional event broadcast blocked in Kenya is accessed from Kenyan IPs using VPNs.
- **Monitoring**: Check for rapid changes in IP country codes (e.g., matching a session moving from UK to Kenya within 10 minutes).
