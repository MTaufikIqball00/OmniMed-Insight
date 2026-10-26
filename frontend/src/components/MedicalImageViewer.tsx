"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Eye,
  EyeOff,
  Layers,
  Maximize2,
  RefreshCw,
  ShieldAlert,
  Sliders,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  AnalysisJobRecord,
  fetchAuthorizedImageBlobUrl,
  MedicalImageRecord,
  XaiMetadata,
} from "@/lib/api";

interface MedicalImageViewerProps {
  image: MedicalImageRecord;
  activeJob: AnalysisJobRecord | null;
}

export default function MedicalImageViewer({
  image,
  activeJob,
}: MedicalImageViewerProps) {
  const [rawBlobUrl, setRawBlobUrl] = useState<string | null>(null);
  const [overlayBlobUrl, setOverlayBlobUrl] = useState<string | null>(null);
  const [loadingImage, setLoadingImage] = useState<boolean>(true);
  const [imageError, setImageError] = useState<string | null>(null);

  const [showOverlay, setShowOverlay] = useState<boolean>(true);
  const [overlayOpacity, setOverlayOpacity] = useState<number>(65);
  const [zoom, setZoom] = useState<number>(100);
  const [panX, setPanX] = useState<number>(0);
  const [panY, setPanY] = useState<number>(0);
  const [invertLut, setInvertLut] = useState<boolean>(false);

  const xaiMeta: XaiMetadata | null = React.useMemo(() => {
    if (!activeJob || activeJob.status !== "COMPLETED") return null;
    try {
      return JSON.parse(activeJob.xai_metadata_json) as XaiMetadata;
    } catch {
      return null;
    }
  }, [activeJob]);

  useEffect(() => {
    let revokedRaw: string | null = null;
    let isMounted = true;
    setLoadingImage(true);
    setImageError(null);

    fetchAuthorizedImageBlobUrl(`/api/images/${image.id}/raw`)
      .then((url) => {
        if (!isMounted) return;
        revokedRaw = url;
        setRawBlobUrl(url);
        setLoadingImage(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setImageError(err instanceof Error ? err.message : "Failed to load scan");
        setLoadingImage(false);
      });

    return () => {
      isMounted = false;
      if (revokedRaw) URL.revokeObjectURL(revokedRaw);
    };
  }, [image.id]);

  useEffect(() => {
    let revokedOverlay: string | null = null;
    let isMounted = true;
    setOverlayBlobUrl(null);

    if (activeJob && activeJob.status === "COMPLETED") {
      fetchAuthorizedImageBlobUrl(`/api/jobs/${activeJob.id}/overlay`)
        .then((url) => {
          if (!isMounted) return;
          revokedOverlay = url;
          setOverlayBlobUrl(url);
        })
        .catch(() => {
          if (!isMounted) return;
          setOverlayBlobUrl(null);
        });
    }

    return () => {
      isMounted = false;
      if (revokedOverlay) URL.revokeObjectURL(revokedOverlay);
    };
  }, [activeJob]);

  const handleResetView = () => {
    setZoom(100);
    setPanX(0);
    setPanY(0);
    setInvertLut(false);
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Top Diagnostic Viewer Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-900 px-4 py-3 text-slate-100">
        <div className="flex items-center gap-2.5">
          <span className="inline-flex items-center rounded-md bg-sky-500/20 px-2.5 py-1 text-xs font-semibold text-sky-300 border border-sky-400/30">
            {image.modality} • {image.body_part}
          </span>
          <div className="text-xs">
            <p className="font-medium text-white">{image.original_filename}</p>
            <p className="text-slate-400">
              {image.width}×{image.height}px • {image.bit_depth}-bit •{" "}
              {image.orientation}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(75, z - 25))}
            className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
            title="Zoom Out"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <span className="min-w-[3.5rem] text-center text-xs font-mono text-slate-200">
            {zoom}%
          </span>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(300, z + 25))}
            className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
            title="Zoom In"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={() => setInvertLut((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              invertLut
                ? "bg-amber-500 text-slate-950"
                : "bg-slate-800 text-slate-200 hover:bg-slate-700"
            }`}
          >
            <Sliders className="h-3.5 w-3.5" />
            {invertLut ? "LUT: Inverted" : "LUT: Standard"}
          </button>

          <button
            type="button"
            onClick={handleResetView}
            className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Reset
          </button>

          {overlayBlobUrl && (
            <button
              type="button"
              onClick={() => setShowOverlay((s) => !s)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                showOverlay
                  ? "bg-sky-500 text-white"
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              {showOverlay ? (
                <>
                  <Eye className="h-3.5 w-3.5" />
                  XAI Heatmap ON
                </>
              ) : (
                <>
                  <EyeOff className="h-3.5 w-3.5" />
                  Unaltered Original Only
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Overlay Opacity & Pan Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-slate-100 px-4 py-2.5 text-xs text-slate-700">
        <div className="flex items-center gap-3">
          <Layers className="h-4 w-4 text-sky-700" />
          <label htmlFor="xai-opacity-slider" className="font-medium">
            Grad-CAM Overlay Opacity:
          </label>
          <input
            id="xai-opacity-slider"
            type="range"
            min={0}
            max={100}
            value={overlayOpacity}
            disabled={!overlayBlobUrl || !showOverlay}
            onChange={(e) => setOverlayOpacity(Number(e.target.value))}
            className="h-2 w-32 cursor-pointer accent-sky-600 disabled:opacity-40"
          />
          <span className="font-mono font-semibold text-slate-900">
            {showOverlay && overlayBlobUrl ? `${overlayOpacity}%` : "0% (Hidden)"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Maximize2 className="h-3.5 w-3.5 text-slate-500" />
          <span>Pan Offset:</span>
          <button
            type="button"
            onClick={() => setPanX((x) => x - 20)}
            className="rounded border border-slate-300 bg-white px-2 py-0.5 hover:bg-slate-50"
          >
            ←
          </button>
          <button
            type="button"
            onClick={() => setPanX((x) => x + 20)}
            className="rounded border border-slate-300 bg-white px-2 py-0.5 hover:bg-slate-50"
          >
            →
          </button>
          <button
            type="button"
            onClick={() => setPanY((y) => y - 20)}
            className="rounded border border-slate-300 bg-white px-2 py-0.5 hover:bg-slate-50"
          >
            ↑
          </button>
          <button
            type="button"
            onClick={() => setPanY((y) => y + 20)}
            className="rounded border border-slate-300 bg-white px-2 py-0.5 hover:bg-slate-50"
          >
            ↓
          </button>
        </div>
      </div>

      {/* Main Viewport Canvas */}
      <div className="relative flex min-h-[380px] items-center justify-center overflow-hidden bg-slate-950 p-4">
        {loadingImage && (
          <div className="flex flex-col items-center gap-2 text-slate-400">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
            <span className="text-xs">
              Verifying access boundary & streaming lossless raster...
            </span>
          </div>
        )}

        {imageError && (
          <div className="flex max-w-md items-start gap-2.5 rounded-lg border border-rose-500/40 bg-rose-950/60 p-4 text-xs text-rose-200">
            <AlertTriangle className="h-5 w-5 shrink-0 text-rose-400" />
            <div>
              <p className="font-semibold">Unable to render medical image</p>
              <p className="mt-1 text-rose-300">{imageError}</p>
            </div>
          </div>
        )}

        {!loadingImage && !imageError && rawBlobUrl && (
          <div
            className="relative select-none transition-transform duration-150"
            style={{
              transform: `translate(${panX}px, ${panY}px) scale(${zoom / 100})`,
            }}
          >
            {/* Original Unaltered Medical Scan */}
            <img
              src={rawBlobUrl}
              alt={`Medical scan ${image.original_filename}`}
              className="max-h-[360px] w-auto rounded border border-slate-800 object-contain"
              style={{
                filter: invertLut ? "invert(1)" : "none",
              }}
            />

            {/* Separate Derived Grad-CAM Heatmap Overlay */}
            {overlayBlobUrl && showOverlay && (
              <img
                src={overlayBlobUrl}
                alt="Grad-CAM Spatial Attribution Overlay"
                className="pointer-events-none absolute inset-0 h-full w-full rounded object-contain"
                style={{
                  opacity: overlayOpacity / 100,
                }}
              />
            )}
          </div>
        )}

        {/* Viewport Corner Metadata HUD */}
        <div className="pointer-events-none absolute bottom-3 left-3 rounded bg-slate-900/85 px-2.5 py-1.5 text-[11px] font-mono text-slate-300 border border-slate-800">
          <div>SHA-256: {image.sha256_digest.slice(0, 16)}…</div>
          <div>
            SOURCE INTEGRITY: UNALTERED READ-ONLY • SYNTHETIC PHANTOM
          </div>
        </div>
      </div>

      {/* Attribution Color Legend & Mandatory Clinical Safety Warning */}
      <div className="border-t border-slate-200 bg-slate-50 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Grad-CAM Feature Attribution Scale (Normalized 0.00 → 1.00)
          </span>
          {xaiMeta && (
            <span className="text-xs font-mono text-slate-600">
              Layer: <strong>{xaiMeta.target_layer}</strong> (
              {xaiMeta.feature_map_resolution} → {xaiMeta.upsampled_resolution})
            </span>
          )}
        </div>

        {/* Thermal Gradient Bar */}
        <div className="space-y-1">
          <div className="h-3 w-full rounded-full bg-gradient-to-r from-blue-900 via-cyan-400 via-50% via-yellow-400 to-red-600 shadow-inner" />
          <div className="flex justify-between text-[11px] font-medium text-slate-600">
            <span>0.00 (Minimal Gradient Contribution)</span>
            <span>0.50 (Moderate Feature Weight)</span>
            <span>1.00 (Peak Class Score Attribution)</span>
          </div>
        </div>

        {xaiMeta && (
          <div className="rounded-lg border border-amber-300 bg-amber-50/90 p-3 text-xs text-amber-950">
            <div className="flex items-start gap-2">
              <ShieldAlert className="h-4 w-4 shrink-0 text-amber-700 mt-0.5" />
              <div className="space-y-1">
                <p className="font-semibold">
                  Explained Output: &ldquo;{xaiMeta.explained_class_label}&rdquo; (
                  <code>{xaiMeta.explained_class_code}</code>)
                </p>
                <p>{xaiMeta.clinical_warning}</p>
                <p className="text-amber-800">{xaiMeta.localization_limitation}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
