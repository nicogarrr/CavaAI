import type { Metadata, Viewport } from "next";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "CavaAI - Research OS de inversión fundamental",
    template: "%s | CavaAI"
  },
  description: "CavaAI convierte evidencia, modelos company-specific y memoria histórica en tesis fundamentales trazables.",
  keywords: ["fundamental analysis", "investment thesis", "financial modeling", "research OS", "análisis fundamental"],
  authors: [{ name: "CavaAI Team" }],
  creator: "CavaAI",
  icons: {
    icon: [
      { url: '/assets/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/assets/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/assets/icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
  },
  robots: {
    index: true,
    follow: true,
  },
  alternates: {
    languages: {
      'es': '/',
      'en': '/',
    },
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  themeColor: '#101010',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="dark" suppressHydrationWarning>
      <body className="antialiased" suppressHydrationWarning>
        {children}
        <Toaster />
        {/* Service worker (app shell + fallback offline). Solo en build de
            producción: en dev las cachés del SW estorban al hot-reload. */}
        {process.env.NODE_ENV === 'production' ? (
          <script
            dangerouslySetInnerHTML={{
              __html: "if ('serviceWorker' in navigator) { window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js'); }); }",
            }}
          />
        ) : null}
      </body>
    </html>
  );
}
