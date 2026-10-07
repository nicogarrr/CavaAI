export type InvestorVideo = {
    video_id: string;
    title: string;
    published_at: string;
    channel_name: string;
    channel_url: string;
    channel_kind: 'personal_confirmed' | 'archive';
};

export function isYouTubeVideoId(value: unknown): value is string {
    return typeof value === 'string' && /^[A-Za-z0-9_-]{11}$/.test(value);
}

/** Solo canales de YouTube HTTPS; nunca un destino arbitrario del payload. */
export function isYouTubeChannelUrl(value: unknown): value is string {
    if (typeof value !== 'string') return false;
    try {
        const url = new URL(value);
        return url.protocol === 'https:' && !url.username && !url.password && !url.port
            && ['www.youtube.com', 'youtube.com'].includes(url.hostname)
            && /^\/(?:@[^/?#]+|channel\/UC[A-Za-z0-9_-]{22})\/?$/.test(url.pathname)
            && !url.search && !url.hash;
    } catch {
        return false;
    }
}

/** El campo es opcional hasta que haya un RSS confirmado para este inversor. */
export function validInvestorVideos(value: unknown): InvestorVideo[] {
    if (!Array.isArray(value)) return [];
    const seen = new Set<string>();
    return value.filter((item): item is InvestorVideo => {
        if (!item || typeof item !== 'object') return false;
        const row = item as Record<string, unknown>;
        if (!isYouTubeVideoId(row.video_id) || seen.has(row.video_id)
            || typeof row.title !== 'string' || !row.title.trim()
            || typeof row.channel_name !== 'string' || !row.channel_name.trim()
            || !['personal_confirmed', 'archive'].includes(String(row.channel_kind))
            || !isYouTubeChannelUrl(row.channel_url)
            || typeof row.published_at !== 'string'
            || !/^\d{4}-\d{2}-\d{2}T/.test(row.published_at)
            || !Number.isFinite(Date.parse(row.published_at))) return false;
        seen.add(row.video_id);
        return true;
    }).sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at)).slice(0, 6);
}
