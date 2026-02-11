/**
 * k6 HTTP load test for Ollqd gateway endpoints.
 *
 * Run: k6 run tests/perf/k6_http.js --env GATEWAY_URL=http://localhost:8000
 *
 * Scenarios:
 *   smoke   — 1 VU, 10 iterations (sanity check)
 *   load    — 10 VUs, 30s ramp-up, 60s sustain, 30s ramp-down
 */

import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE = __ENV.GATEWAY_URL || "http://localhost:8000";

// Custom metrics
const errorRate = new Rate("errors");
const healthLatency = new Trend("health_latency", true);
const collectionsLatency = new Trend("collections_latency", true);
const searchLatency = new Trend("search_latency", true);

export const options = {
  scenarios: {
    smoke: {
      executor: "shared-iterations",
      vus: 1,
      iterations: 10,
      maxDuration: "30s",
      tags: { scenario: "smoke" },
    },
    load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "15s", target: 10 },
        { duration: "30s", target: 10 },
        { duration: "15s", target: 0 },
      ],
      tags: { scenario: "load" },
      startTime: "35s", // start after smoke
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<2000"], // 95th percentile under 2s
    errors: ["rate<0.1"], // error rate under 10%
    health_latency: ["p(99)<500"],
    collections_latency: ["p(99)<1000"],
  },
};

export default function () {
  group("health", () => {
    const res = http.get(`${BASE}/api/system/health`);
    const ok = check(res, {
      "health status 200": (r) => r.status === 200,
      "health has status field": (r) => {
        try {
          return JSON.parse(r.body).status !== undefined;
        } catch {
          return false;
        }
      },
    });
    errorRate.add(!ok);
    healthLatency.add(res.timings.duration);
  });

  group("collections_list", () => {
    const res = http.get(`${BASE}/api/qdrant/collections`);
    const ok = check(res, {
      "collections status 200": (r) => r.status === 200,
    });
    errorRate.add(!ok);
    collectionsLatency.add(res.timings.duration);
  });

  group("config", () => {
    const res = http.get(`${BASE}/api/system/config`);
    check(res, {
      "config status 200": (r) => r.status === 200,
    });
  });

  group("search_empty", () => {
    const payload = JSON.stringify({
      query: "test query for load testing",
      collection: "nonexistent_perf_test",
      limit: 5,
    });
    const params = { headers: { "Content-Type": "application/json" } };
    const res = http.post(`${BASE}/api/rag/search`, payload, params);
    // May return 400/404/500 if collection doesn't exist — that's OK for load testing
    searchLatency.add(res.timings.duration);
  });

  group("models_list", () => {
    const res = http.get(`${BASE}/api/ollama/api/tags`);
    check(res, {
      "models responds": (r) => r.status < 500,
    });
  });

  sleep(0.5);
}

export function handleSummary(data) {
  return {
    "../../../artifacts/results/k6-summary.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: "  ", enableColors: true }),
  };
}

// Inline text summary (k6 doesn't export it by default in all versions)
function textSummary(data, opts) {
  const lines = [];
  lines.push("=== k6 Load Test Summary ===\n");

  if (data.metrics) {
    for (const [name, metric] of Object.entries(data.metrics)) {
      if (metric.values) {
        const v = metric.values;
        if (v.avg !== undefined) {
          lines.push(
            `  ${name}: avg=${v.avg.toFixed(2)}ms p95=${(v["p(95)"] || 0).toFixed(2)}ms max=${(v.max || 0).toFixed(2)}ms`,
          );
        } else if (v.rate !== undefined) {
          lines.push(`  ${name}: rate=${(v.rate * 100).toFixed(1)}%`);
        } else if (v.value !== undefined) {
          lines.push(`  ${name}: ${v.value}`);
        }
      }
    }
  }
  return lines.join("\n") + "\n";
}
