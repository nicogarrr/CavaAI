import { MetadataRoute } from 'next'
 
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/_next/', '/sign-in', '/sign-up'],
      },
    ],
    sitemap: `${process.env.BETTER_AUTH_URL || 'REDACTED_BY_AUDIT'}/sitemap.xml`,
  }
}
