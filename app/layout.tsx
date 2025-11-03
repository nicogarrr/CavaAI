import type { Metadata } from "next";
import {Toaster} from "@/components/ui/sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "JLCavaAI",
  description: "JLCavaAI es una plataforma inteligente de seguimiento de mercados y gestión de carteras. Analiza precios en tiempo real, gestiona tu portfolio personalizado, y accede a insights detallados de empresas y ETFs — construido con tecnología de vanguardia.",
};

export default function RootLayout({
                                       children,
                                   }: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" className="dark">
            <body className="antialiased">
                {children}
                <Toaster/>
            </body>
        </html>
    );
}
