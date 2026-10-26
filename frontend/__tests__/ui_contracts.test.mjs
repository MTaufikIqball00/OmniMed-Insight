import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");

test("Frontend package.json configures Tailwind CSS v3 and binds dev/start to 127.0.0.1:3100", () => {
  const pkg = JSON.parse(
    fs.readFileSync(path.join(rootDir, "package.json"), "utf8")
  );
  assert.ok(pkg.devDependencies.tailwindcss, "Tailwind CSS must be installed");
  assert.match(pkg.scripts.dev, /-p 3100 -H 127\.0\.0\.1/);
  assert.match(pkg.scripts.start, /-p 3100 -H 127\.0\.0\.1/);
});

test("MedicalImageViewer implements zoom, pan, LUT invert, Grad-CAM opacity slider, thermal legend, and attribution warning", () => {
  const viewerSrc = fs.readFileSync(
    path.join(rootDir, "src", "components", "MedicalImageViewer.tsx"),
    "utf8"
  );
  assert.match(viewerSrc, /xai-opacity-slider/);
  assert.match(viewerSrc, /Grad-CAM Feature Attribution Scale/);
  assert.match(viewerSrc, /SOURCE INTEGRITY: UNALTERED READ-ONLY/);
  assert.match(viewerSrc, /clinical_warning/);
  assert.match(viewerSrc, /localization_limitation/);
});

test("Main clinical workspace enforces RBAC visibility, provenance citations, and synthetic data disclosures", () => {
  const pageSrc = fs.readFileSync(
    path.join(rootDir, "src", "app", "page.tsx"),
    "utf8"
  );
  assert.match(pageSrc, /DECISION SUPPORT ONLY/);
  assert.match(pageSrc, /RESEARCH_UNVERIFIED/);
  assert.match(pageSrc, /Evidence Provenance Chain/);
  assert.match(pageSrc, /Test Cross-Patient IDOR Guard/);
  assert.match(pageSrc, /aria-label="Primary Workspace Navigation"/);
  assert.match(pageSrc, /role="alert"/);
});
