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
      </body>
    </html>
  );
}
