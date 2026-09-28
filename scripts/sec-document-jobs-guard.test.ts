import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const config = readFileSync("data-engine/app/core/config.py", "utf8");
const workers = readFileSync("data-engine/app/workers/dramatiq_app.py", "utf8");

test("SEC document jobs gated behind sec_document_jobs_enabled, default off", () => {
  // OCI's IP is permanently 403-blocked by the SEC; emitting document jobs
  // from prod always fails and poisoned the default queue (F359).
  assert.match(config, /sec_document_jobs_enabled: bool = False/, "flag default False");
  assert.match(workers, /if settings\.sec_document_jobs_enabled:/, "emission gated");
  assert.match(workers, /skipped_documents \+= sum\(1 for item in result\.items if item\.url\)/, "skip counted");
  assert.match(workers, /"documents_skipped_sec_blocked": skipped_documents/, "skip visible in payload");
});
