/**
 * QoE Telemetry & Observability SDK for GNTV Digital (Sprint 6.5).
 */

export class TelemetryCollector {
  constructor(apiBaseUrl, sessionId) {
    this.apiBaseUrl = (apiBaseUrl || "http://localhost:8000").replace(/\/$/, "");
    this.sessionId = sessionId;
    this.sequenceNumber = 0;
    this.eventQueue = [];
    this.flushIntervalMs = 10000;
    this.maxBatchSize = 20;
    this.timer = null;

    this.initFlushTimer();
    this.setupUnloadHandler();
  }

  initFlushTimer() {
    if (typeof window !== "undefined") {
      this.timer = window.setInterval(() => this.flush(), this.flushIntervalMs);
    }
  }

  setupUnloadHandler() {
    if (typeof window === "undefined") return;
    const handleUnload = () => this.flushBeacon();
    window.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") handleUnload();
    });
    window.addEventListener("pagehide", handleUnload);
  }

  track(eventType, positionMs = 0, bitrateBps = null, fps = null, errorCode = null, metadata = {}) {
    if (!this.sessionId) return;

    const event = {
      event_type: eventType,
      timestamp_ms: Date.now(),
      position_ms: Math.max(0, Math.round(positionMs)),
      bitrate_bps: bitrateBps ? Math.round(bitrateBps) : null,
      fps: fps ? Number(fps.toFixed(2)) : null,
      error_code: errorCode || null,
      metadata: metadata || {},
    };

    this.eventQueue.push(event);

    if (this.eventQueue.length >= this.maxBatchSize) {
      this.flush();
    }
  }

  async flush() {
    if (this.eventQueue.length === 0 || !this.sessionId) return;

    const eventsToFlush = [...this.eventQueue];
    this.eventQueue = [];

    const payload = {
      session_id: this.sessionId,
      sequence_number: ++this.sequenceNumber,
      client_timestamp_ms: Date.now(),
      events: eventsToFlush,
    };

    try {
      const resp = await fetch(`${this.apiBaseUrl}/api/v1/streaming/telemetry/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true,
      });

      if (resp.ok) {
        const data = await resp.json();
        if (data.next_flush_interval_ms) {
          this.flushIntervalMs = data.next_flush_interval_ms;
        }
      }
    } catch {
      // Re-queue un-sent events for retry
      this.eventQueue = [...eventsToFlush, ...this.eventQueue].slice(0, 100);
    }
  }

  flushBeacon() {
    if (this.eventQueue.length === 0 || !this.sessionId) return;

    const payload = {
      session_id: this.sessionId,
      sequence_number: ++this.sequenceNumber,
      client_timestamp_ms: Date.now(),
      events: this.eventQueue,
    };
    this.eventQueue = [];

    const url = `${this.apiBaseUrl}/api/v1/streaming/telemetry/batch`;
    const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });

    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, blob);
    }
  }

  destroy() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.flushBeacon();
  }
}
