"use client";

import React, { useEffect } from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("OmniMed App Runtime Exception:", error);
  }, [error]);

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="max-w-md w-full rounded-2xl border border-rose-200 bg-white p-6 shadow-xl space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-rose-100 text-rose-600">
            <AlertTriangle className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Terjadi Kesalahan Aplikasi
            </h2>
            <p className="text-xs text-slate-500">
              OmniMed Insight Runtime Guard
            </p>
          </div>
        </div>
        <p className="text-sm text-slate-600">
          Aplikasi mendeteksi pengecualian pada browser client. Seluruh data pasien dan model backend tetap aman.
        </p>
        {error?.message && (
          <div className="rounded-lg bg-rose-50 border border-rose-100 p-3 font-mono text-xs text-rose-800 break-all">
            {error.message}
          </div>
        )}
        <div className="flex gap-2 pt-2">
          <button
            type="button"
            onClick={() => reset()}
            className="flex-1 inline-flex justify-center items-center gap-2 rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-teal-700 transition"
          >
            <RefreshCw className="h-4 w-4" />
            Coba Pulihkan
          </button>
          <button
            type="button"
            onClick={() => {
              window.location.href = "/";
            }}
            className="inline-flex justify-center items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition"
          >
            <Home className="h-4 w-4" />
            Beranda
          </button>
        </div>
      </div>
    </div>
  );
}
