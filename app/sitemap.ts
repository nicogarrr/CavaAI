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

  // Sin `lastModified`: las tres páginas son rutas estáticas sin fecha de
  // edición real en un dato. `lastModified: new Date()` decía «modificado
  // ahora» en contenido que no cambia, TODOS los días: una afirmación de
  // frescura falsa en el canal que leen los buscadores. Sin la clave, el
  // buscador trata la fecha como desconocida, que es la verdad.
  return [
    {
      url: `${base}/`,
      changeFrequency: 'weekly',
      priority: 0.9,
    },
    {
      url: `${base}/metodologia`,
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: `${base}/help`,
      changeFrequency: 'monthly',
      priority: 0.5,
    },
  ];
  // /terms queda fuera del sitemap a propósito: la página es pública pero
  // noindex hasta que el texto legal (Dic 2024) se valide; incluirla aquí
  // empujaría a indexarla.
}
