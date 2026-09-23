import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    distDir: process.env.NEXT_DIST_DIR ?? '.next',
    devIndicators: false,
    /* Performance optimizations */
    compress: true, // Enable gzip compression
    productionBrowserSourceMaps: false, // Disable source maps in production for smaller bundle
    
    // Configuración vacía para Turbopack (Next.js 16+)
    // Necesario para evitar error de build con config webpack legacy
    turbopack: {},
    
    // Optimize images
    images: {
        remotePatterns: [
            {
                protocol: 'https',
                hostname: 'i.ibb.co',
                port: '',
                pathname: '/**',
            },
        ],
        formats: ['image/webp', 'image/avif'], // Modern formats for better performance
        deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048, 3840],
        imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
    },
    
    // Optimize bundling
    experimental: {
        optimizePackageImports: ['lucide-react', 'recharts'], // Tree-shake large dependencies
        serverActions: {
            // 4mb: Vercel Hobby corta el body de las server actions en ~4.5 MB;
            // un límite mayor solo cambia el error local por un fallo silencioso
            // en producción. La UI avisa al elegir archivos > 4 MB
            // (components/forms/FileUploadInput.tsx).
            bodySizeLimit: '4mb',
        },
    },
    
    typescript: {
        ignoreBuildErrors: false, // Habilitar verificación de TypeScript
    },
    
    // Docker needs standalone output; Vercel packages Next.js itself.
    ...(process.env.VERCEL ? {} : { output: 'standalone' as const }),
    
    // Headers for better caching and security
    async headers() {
        return [
            {
                source: '/:path*',
                headers: [
                    {
                        key: 'X-DNS-Prefetch-Control',
                        value: 'on'
                    },
                    {
                        key: 'X-Frame-Options',
                        value: 'SAMEORIGIN'
                    },
                    {
                        key: 'X-Content-Type-Options',
                        value: 'nosniff'
                    },
                    {
                        key: 'Referrer-Policy',
                        value: 'strict-origin-when-cross-origin'
                    },
                    {
                        key: 'Permissions-Policy',
                        value: 'camera=(), microphone=(), geolocation=()'
                    },
                ],
            },
        ];
    },
};

export default nextConfig;
