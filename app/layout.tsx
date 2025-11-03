import type { Metadata, Viewport } from "next";
import {Toaster} from "@/components/ui/sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "JLCavaAI - Plataforma de Análisis de Mercados",
    template: "%s | JLCavaAI"
  },
  description: "JLCavaAI es una plataforma inteligente de seguimiento de mercados. Analiza precios en tiempo real y accede a insights detallados de empresas y ETFs — construido con tecnología de vanguardia.",
  keywords: ["stock analysis", "market data", "financial analysis", "ETF analysis", "real-time prices", "análisis de acciones", "datos de mercado"],
  authors: [{ name: "JLCavaAI Team" }],
  creator: "JLCavaAI",
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
        <html lang="es" className="dark">
            <body className="antialiased">
                {children}
                <Toaster/>
            </body>
        </html>
    );
}
