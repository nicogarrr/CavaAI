import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
            bodySizeLimit: '20mb', // Máximo que soporta Gemini API
        },
    },
    
    typescript: {
        ignoreBuildErrors: false, // Habilitar verificación de TypeScript
    },
    
    // Configuración para Docker (standalone output)
    output: 'standalone',
    
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
