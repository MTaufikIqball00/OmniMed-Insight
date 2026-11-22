"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Columns,
  Crosshair,
  Eye,
  EyeOff,
  HelpCircle,
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

  const [viewMode, setViewMode] = useState<"overlay" | "split" | "original">(
    "overlay"
  );
  const [overlayOpacity, setOverlayOpacity] = useState<number>(48);
  const [showPeakMarker, setShowPeakMarker] = useState<boolean>(true);
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
    setOverlayOpacity(48);
  };

  const showOverlay = viewMode !== "original" && Boolean(overlayBlobUrl);
  const peakX = xaiMeta?.peak_coords_norm?.[0];
  const peakY = xaiMeta?.peak_coords_norm?.[1];
  const hasPeakCoords =
    typeof peakX === "number" &&
    typeof peakY === "number" &&
    !isNaN(peakX) &&
    !isNaN(peakY);

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
            <div className="inline-flex rounded-lg bg-slate-800 p-0.5 border border-slate-700">
              <button
                type="button"
                onClick={() => setViewMode("overlay")}
                className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                  viewMode === "overlay"
                    ? "bg-sky-500 text-white"
                    : "text-slate-300 hover:text-white"
                }`}
              >
                <Eye className="h-3.5 w-3.5" />
                Overlay
              </button>
              <button
                type="button"
                onClick={() => setViewMode("split")}
                className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                  viewMode === "split"
                    ? "bg-sky-500 text-white"
                    : "text-slate-300 hover:text-white"
                }`}
                title="Bandingkan Foto Asli vs Peta Fokus AI berdampingan"
              >
                <Columns className="h-3.5 w-3.5" />
                Bandingkan
              </button>
              <button
                type="button"
                onClick={() => setViewMode("original")}
                className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                  viewMode === "original"
                    ? "bg-amber-500 text-slate-950"
                    : "text-slate-300 hover:text-white"
                }`}
                title="Tampilkan foto asli murni tanpa warna XAI"
              >
                <EyeOff className="h-3.5 w-3.5" />
                Asli Saja
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Overlay Opacity, Crosshair & Pan Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-slate-100 px-4 py-2.5 text-xs text-slate-700">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-sky-700" />
            <label htmlFor="xai-opacity-slider" className="font-medium">
              Transparansi Warna XAI:
            </label>
            <input
              id="xai-opacity-slider"
              type="range"
              min={0}
              max={100}
              value={overlayOpacity}
              disabled={!overlayBlobUrl || viewMode === "original"}
              onChange={(e) => setOverlayOpacity(Number(e.target.value))}
              className="h-2 w-28 cursor-pointer accent-sky-600 disabled:opacity-40"
            />
            <span className="font-mono font-semibold text-slate-900 min-w-[3.2rem]">
              {showOverlay ? `${overlayOpacity}%` : "0%"}
            </span>
          </div>

          {hasPeakCoords && overlayBlobUrl && viewMode !== "original" && (
            <button
              type="button"
              onClick={() => setShowPeakMarker((p) => !p)}
              className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-medium transition ${
                showPeakMarker
                  ? "border-rose-300 bg-rose-50 text-rose-800"
                  : "border-slate-300 bg-white text-slate-600"
              }`}
            >
              <Crosshair className="h-3 w-3" />
              {showPeakMarker ? "Titik Puncak: ON" : "Titik Puncak: OFF"}
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Maximize2 className="h-3.5 w-3.5 text-slate-500" />
          <span>Geser:</span>
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
              Verifying access boundary &amp; streaming lossless raster...
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

        {!loadingImage && !imageError && rawBlobUrl && viewMode === "split" && (
          <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
            {/* Left Side: Unaltered Clean Original */}
            <div className="flex flex-col items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/60 p-2">
              <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-200">
                1. Foto Medis Asli (Tanpa Warna AI)
              </span>
              <div
                className="relative select-none overflow-hidden transition-transform duration-150"
                style={{
                  transform: `translate(${panX}px, ${panY}px) scale(${zoom / 100})`,
                }}
              >
                <img
                  src={rawBlobUrl}
                  alt={`Original scan ${image.original_filename}`}
                  className="max-h-[320px] w-auto rounded object-contain"
                  style={{ filter: invertLut ? "invert(1)" : "none" }}
                />
              </div>
            </div>

            {/* Right Side: With XAI Heatmap & Peak Crosshair */}
            <div className="flex flex-col items-center gap-1.5 rounded-lg border border-sky-500/30 bg-slate-900/60 p-2">
              <span className="rounded bg-sky-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-300">
                2. Titik Fokus Perhatian AI (Grad-CAM {overlayOpacity}%)
              </span>
              <div
                className="relative select-none overflow-hidden transition-transform duration-150"
                style={{
                  transform: `translate(${panX}px, ${panY}px) scale(${zoom / 100})`,
                }}
              >
                <img
                  src={rawBlobUrl}
                  alt={`Medical scan overlay ${image.original_filename}`}
                  className="max-h-[320px] w-auto rounded object-contain"
                  style={{ filter: invertLut ? "invert(1)" : "none" }}
                />
                {overlayBlobUrl && (
                  <img
                    src={overlayBlobUrl}
                    alt="Grad-CAM Spatial Attribution Overlay"
                    className="pointer-events-none absolute inset-0 h-full w-full rounded object-contain"
                    style={{ opacity: overlayOpacity / 100 }}
                  />
                )}
                {showPeakMarker && hasPeakCoords && (
                  <div
                    className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
                    style={{ left: `${peakX * 100}%`, top: `${peakY * 100}%` }}
                  >
                    <div className="h-7 w-7 rounded-full border-2 border-dashed border-white shadow-[0_0_8px_rgba(0,0,0,0.9)]" />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {!loadingImage && !imageError && rawBlobUrl && viewMode !== "split" && (
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
            {showOverlay && overlayBlobUrl && (
              <img
                src={overlayBlobUrl}
                alt="Grad-CAM Spatial Attribution Overlay"
                className="pointer-events-none absolute inset-0 h-full w-full rounded object-contain"
                style={{
                  opacity: overlayOpacity / 100,
                }}
              />
            )}

            {/* Peak Focus Marker */}
            {showOverlay && showPeakMarker && hasPeakCoords && (
              <div
                className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
                style={{ left: `${peakX * 100}%`, top: `${peakY * 100}%` }}
                title={`Titik fokus tertinggi AI (${Math.round(peakX * 100)}%, ${Math.round(peakY * 100)}%)`}
              >
                <div className="h-8 w-8 rounded-full border-2 border-dashed border-white shadow-[0_0_8px_rgba(0,0,0,0.85)]" />
                <span className="mt-1 block whitespace-nowrap rounded bg-slate-900/85 px-1.5 py-0.5 text-[9px] font-bold text-white border border-white/30">
                  Fokus Puncak AI
                </span>
              </div>
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

      {/* Attribution Color Legend, Plain-Language Reading Guide & Clinical Warning */}
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
          <div className="h-3 w-full rounded-full bg-gradient-to-r from-slate-200 via-cyan-400 via-45% via-yellow-400 to-red-600 shadow-inner" />
          <div className="flex justify-between text-[11px] font-medium text-slate-600">
            <span>0.00 – 0.23 (Transparan / Normal)</span>
            <span>0.50 (Pengaruh Sedang)</span>
            <span>1.00 (Fokus Puncak AI)</span>
          </div>
        </div>

        {/* Beginner-Friendly Color Reading Guide */}
        <div className="rounded-lg border border-sky-200 bg-white p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-sky-950">
            <HelpCircle className="h-4 w-4 text-sky-600" />
            Cara Mudah Membaca Warna XAI (Agar Tidak Bingung):
          </div>
          <div className="grid grid-cols-1 gap-2 text-[11px] sm:grid-cols-3">
            <div className="flex items-start gap-2 rounded bg-slate-50 p-2 border border-slate-200">
              <span className="mt-0.5 h-3 w-3 shrink-0 rounded-full border border-slate-400 bg-white" />
              <div>
                <strong className="text-slate-900">Bening (Tanpa Warna):</strong>
                <p className="text-slate-600">
                  Jaringan normal atau area yang dianggap wajar oleh AI. Foto asli tetap terlihat jelas.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-2 rounded bg-amber-50/70 p-2 border border-amber-200">
              <span className="mt-0.5 h-3 w-3 shrink-0 rounded-full bg-amber-400" />
              <div>
                <strong className="text-amber-950">Biru / Hijau / Kuning:</strong>
                <p className="text-amber-900/80">
                  Area pendukung. AI mulai membandingkan kepadatan atau asimetri di sekitar zona ini.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-2 rounded bg-rose-50/80 p-2 border border-rose-200">
              <span className="mt-0.5 h-3 w-3 shrink-0 rounded-full bg-rose-600" />
              <div>
                <strong className="text-rose-950">Merah Terang + Lingkaran:</strong>
                <p className="text-rose-900/80">
                  Area paling diperhatikan AI saat memilih kesimpulan. Wajib diperiksa ulang dengan klik tombol <strong>&ldquo;Bandingkan&rdquo;</strong>.
                </p>
              </div>
            </div>
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
