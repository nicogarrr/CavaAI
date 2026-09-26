import { MetadataRoute } from 'next';

import { siteUrl } from '@/lib/config/site';

/**
 * Solo las rutas públicas.
 *
 * `/propicks` estaba aquí y es una de las pantallas autenticadas: anunciarla en
 * el sitemap invita a los buscadores a indexar un módulo privado. El árbol
 * público es el de `app/(public)`: landing, metodología, términos y ayuda.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteUrl();

  return [
    {
      url: `${base}/`,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 0.9,
    },
    {
      url: `${base}/metodologia`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: `${base}/help`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.5,
    },
    {
      url: `${base}/terms`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
  ];
}
