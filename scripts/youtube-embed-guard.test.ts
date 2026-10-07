import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
// @ts-expect-error TS5097: extensión necesaria para node --experimental-strip-types.
import { isYouTubeVideoId, isYouTubeChannelUrl, validInvestorVideos } from '../lib/ui/youtube-video.ts';

const video = {
    video_id: 'aB_12-cDE34', title: 'Una entrevista', published_at: '2026-10-06T15:00:00Z',
    channel_kind: 'personal_confirmed', channel_name: 'Canal', channel_url: 'https://www.youtube.com/@canal',
};

describe('vídeos de inversores', () => {
    it('limita el ID y los destinos a YouTube', () => {
        assert.equal(isYouTubeVideoId(video.video_id), true);
        for (const id of ['', '../watch?v=x', 'bad?id=1234', null]) assert.equal(isYouTubeVideoId(id), false);
        assert.equal(isYouTubeChannelUrl(video.channel_url), true);
        assert.equal(isYouTubeChannelUrl('https://www.youtube.com/channel/UCIALMKvObZNtJ6AmdCLP7Lg'), true);
        for (const url of ['https://youtube.com.evil.test/@canal', 'javascript:alert(1)', 'http://www.youtube.com/@canal', 'https://user@youtube.com/@canal', 'https://youtube.com/watch?v=aB_12-cDE34']) {
            assert.equal(isYouTubeChannelUrl(url), false);
        }
    });
    it('sin datos y payloads inválidos no inventan vídeos', () => {
        for (const data of [undefined, null, {}, [], [null], [{ ...video, published_at: 'bad' }], [{ ...video, title: ' ' }], [{ ...video, channel_kind: undefined }], [{ ...video, channel_kind: 'unknown' }], [{ ...video, channel_url: 'https://evil.test' }]]) {
            assert.deepEqual(validInvestorVideos(data), []);
        }
    });
    it('deduplica, ordena recientes y limita a seis', () => {
        assert.equal(validInvestorVideos([video, video]).length, 1);
        const old = { ...video, video_id: 'bB_12-cDE34', published_at: '2026-10-05T12:00:00Z' };
        assert.deepEqual(validInvestorVideos([old, video]).map((v) => v.video_id), [video.video_id, old.video_id]);
        const many = Array.from({ length: 8 }, (_, i) => ({ ...video, video_id: `${i}B_12-cDE34` }));
        assert.equal(validInvestorVideos(many).length, 6);
    });
    it('CSP permite los reproductores de YouTube explícitamente', () => {
        const config = readFileSync('next.config.ts', 'utf8');
        assert.match(config, /frame-src https:\/\/www\.youtube-nocookie\.com https:\/\/www\.youtube\.com;/);
        assert.match(config, /frame-ancestors 'self'/);
    });
    it('iframe solo tras clic, nocookie, con título y alternativa externa', () => {
        const embed = readFileSync('components/media/YouTubeEmbed.tsx', 'utf8');
        assert.match(embed, /useState\(false\)/);
        assert.match(embed, /onClick=\{\(\) => setLoaded\(true\)\}/);
        assert.match(embed, /https:\/\/www\.youtube-nocookie\.com\/embed\//);
        assert.match(embed, /title=\{title\}/);
        assert.match(embed, /isYouTubeVideoId\(videoId\)/);
        const block = readFileSync('app/(root)/inversores/_components/InvestorVideos.tsx', 'utf8');
        assert.match(block, /Sin datos/);
        assert.match(block, /Fuente:/);
        assert.match(block, /video\.channel_kind === 'archive'/);
        assert.match(block, /Archivo, fuente no confirmada/);
        assert.match(block, /<time dateTime=/);
        assert.match(block, /Ver en YouTube/);
        assert.match(readFileSync('app/(root)/inversores/[slug]/page.tsx', 'utf8'), /<InvestorVideos videos=\{investor\.videos\}/);
    });
});
