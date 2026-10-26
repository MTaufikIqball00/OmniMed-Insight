import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniMed Insight (XAI) — Multimodal Clinical Decision Support",
  description:
    "Explainable Medical Imaging (Grad-CAM), Evidence-Grounded Report Drafting, FHIR R4 Interoperability, and RBAC Security Platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              window.addEventListener('error', function(e) {
                if (e.filename && e.filename.indexOf('chrome-extension://') !== -1) {
                  e.stopImmediatePropagation();
                  e.preventDefault();
                }
              }, true);
            `,
          }}
        />
      </head>
      <body className="min-h-screen bg-slate-50 text-slate-900">
        {children}
      </body>
    </html>
  );
}
