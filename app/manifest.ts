import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: 'CavaAI — Research OS de inversión',
    short_name: 'CavaAI',
    description: 'Tu memoria de inversor a largo plazo: tesis, alertas y cartera.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: '#101010',
    theme_color: '#101010',
    lang: 'es',
    dir: 'ltr',
    categories: ['finance', 'business'],
    icons: [
      { src: '/assets/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/assets/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
      {
        src: '/assets/icons/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
    // Provisionales: reutilizan el icono 512 (fichero existente) hasta contar
    // con capturas dedicadas de 1080x1920 (narrow) y 1920x1080 (wide).
    screenshots: [
      {
        src: '/assets/icons/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
        form_factor: 'narrow',
      },
      {
        src: '/assets/icons/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
        form_factor: 'wide',
      },
    ],
  };
}
