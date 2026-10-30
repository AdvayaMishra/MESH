import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Toaster } from "sonner";
import "./globals.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { default: "MESH — One platform. Every team. Total visibility.", template: "%s · MESH" },
  description:
    "MESH brings people, projects, operations and cybersecurity together in one intelligent workspace.",
};

export const viewport: Viewport = { themeColor: "#F8FAFF", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="min-h-dvh bg-canvas text-ink">
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast: "!rounded-2xl !border !border-line !shadow-pop !font-sans",
            },
          }}
        />
      </body>
    </html>
  );
}
