'use server';

import { getRAGContext } from './ai.actions';

/**
 * Analisis de sentimiento de noticias y menciones
 * Usa Gemini AI para analizar sentimiento de texto
 */

export interface SentimentScore {
  symbol: string;
  sentiment: 'positive' | 'negative' | 'neutral';
  score: number; // -1 a 1, donde 1 es muy positivo y -1 es muy negativo
  confidence: number; // 0 a 1
  source: 'news' | 'social' | 'combined';
  analyzedText: string;
  keyPhrases?: string[];
  timestamp: string;
}

export interface NewsSentimentAnalysis {
  symbol: string;
  companyName: string;
  overallSentiment: 'positive' | 'negative' | 'neutral';
  overallScore: number;
  articleCount: number;
  sentimentBreakdown: {
    positive: number;
    negative: number;
    neutral: number;
  };
  articles: Array<{
    headline: string;
    summary?: string;
    sentiment: SentimentScore['sentiment'];
    score: number;
    date: string;
    source: string;
  }>;
  keyThemes: string[]; // Temas principales identificados
  timestamp: string;
}

/**
 * Analiza el sentimiento de una noticia individual usando Gemini
 */
async function analyzeNewsSentimentWithAI(
  symbol: string,
  headline: string,
  summary?: string,
  ragContext?: string
): Promise<SentimentScore | null> {
  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    console.warn('No Gemini API key for sentiment analysis');
    return null;
  }

  try {
    const text = summary || headline;

    const prompt = `Eres un analista de sentimiento financiero. Analiza el siguiente texto sobre ${symbol} y determina el sentimiento.

TEXTO:
"${text}"

${ragContext ? `CONTEXTO ADICIONAL (Preferencia de Usuario/Analisis Previos):\n${ragContext}\n` : ''}

RESPONDE EN FORMATO JSON EXACTO:
{
  "sentiment": "positive" | "negative" | "neutral",
  "score": numero entre -1 y 1 (1 = muy positivo, -1 = muy negativo),
  "confidence": numero entre 0 y 1 (que tan seguro estas),
  "keyPhrases": ["frase1", "frase2"] (frases clave que influyeron en el sentimiento)
}

IMPORTANTE:
- Se objetivo e imparcial
- Analiza SOLO el texto proporcionado
- NO uses informacion externa
- El sentimiento debe reflejar como afecta esto a ${symbol}`;

    const payload = {
      contents: [{
        role: 'user',
        parts: [{ text: prompt }],
      }],
    };

    const model = 'gemini-3-flash-preview';
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });

    if (!response.ok) {
      console.warn('Gemini sentiment analysis failed:', response.status);
      return null;
    }

    const json = await response.json();
    const responseText = json?.candidates?.[0]?.content?.parts?.[0]?.text;

    if (!responseText) return null;

    // Extraer JSON de la respuesta
    const jsonMatch = responseText.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return null;

    const result = JSON.parse(jsonMatch[0]);

    return {
      symbol,
      sentiment: result.sentiment || 'neutral',
      score: result.score || 0,
      confidence: result.confidence || 0.5,
      source: 'news',
      analyzedText: responseText,
      keyPhrases: result.keyPhrases || [],
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    console.error('Error analyzing news sentiment:', error);
    return null;
  }
}

/**
 * Analiza el sentimiento de multiples noticias de una empresa
 */
export async function analyzeNewsSentiment(
  symbol: string,
  companyName: string,
  newsArticles: Array<{
    headline: string;
    summary?: string;
    datetime?: number;
    source?: string;
  }>
): Promise<NewsSentimentAnalysis | null> {
  if (!newsArticles || newsArticles.length === 0) {
    return null;
  }

  try {
    // Analizar las ultimas 10 noticias mas relevantes
    const articlesToAnalyze = newsArticles.slice(0, 10);
    const sentimentScores: SentimentScore[] = [];

    // RAG: obtener contexto para el analisis de sentimiento
    const ragContext = await getRAGContext(symbol, companyName);

    // Analizar cada noticia con limite de rate para no sobrecargar API
    for (const article of articlesToAnalyze) {
      const sentiment = await analyzeNewsSentimentWithAI(
        symbol,
        article.headline,
        article.summary,
        ragContext
      );

      if (sentiment) {
        sentimentScores.push(sentiment);
      }

      // Pausa breve para evitar rate limiting
      await new Promise(resolve => setTimeout(resolve, 200));
    }

    if (sentimentScores.length === 0) {
      return null;
    }

    // Calcular sentimiento general
    const avgScore = sentimentScores.reduce((sum, s) => sum + s.score, 0) / sentimentScores.length;
    const positiveCount = sentimentScores.filter(s => s.sentiment === 'positive').length;
    const negativeCount = sentimentScores.filter(s => s.sentiment === 'negative').length;
    const neutralCount = sentimentScores.filter(s => s.sentiment === 'neutral').length;

    let overallSentiment: 'positive' | 'negative' | 'neutral';
    if (avgScore > 0.2) {
      overallSentiment = 'positive';
    } else if (avgScore < -0.2) {
      overallSentiment = 'negative';
    } else {
      overallSentiment = 'neutral';
    }

    // Extraer frases clave de todos los analisis
    const allKeyPhrases = sentimentScores
      .flatMap(s => s.keyPhrases || [])
      .filter((phrase, index, arr) => arr.indexOf(phrase) === index)
      .slice(0, 5);

    // Formatear articulos analizados
    const articles = sentimentScores.map((sentiment, idx) => {
      const article = articlesToAnalyze[idx];
      const date = article.datetime
        ? new Date(article.datetime * 1000).toISOString()
        : new Date().toISOString();

      return {
        headline: article.headline,
        summary: article.summary,
        sentiment: sentiment.sentiment,
        score: sentiment.score,
        date,
        source: article.source || 'Unknown',
      };
    });

    return {
      symbol,
      companyName,
      overallSentiment,
      overallScore: avgScore,
      articleCount: sentimentScores.length,
      sentimentBreakdown: {
        positive: positiveCount,
        negative: negativeCount,
        neutral: neutralCount,
      },
      articles,
      keyThemes: allKeyPhrases,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    console.error('Error analyzing news sentiment:', error);
    return null;
  }
}

/**
 * Analiza sentimiento de menciones sociales proporcionadas por el caller.
 */
const SOCIAL_POSITIVE_TERMS = [
  'beat',
  'beats',
  'bullish',
  'upside',
  'growth',
  'profitable',
  'record',
  'strong',
  'upgrade',
  'buyback',
  'partnership',
  'guidance raised',
];

const SOCIAL_NEGATIVE_TERMS = [
  'miss',
  'misses',
  'bearish',
  'downside',
  'dilution',
  'lawsuit',
  'downgrade',
  'weak',
  'fraud',
  'guidance cut',
  'bankruptcy',
  'delay',
];

export async function analyzeSocialSentiment(
  symbol: string,
  socialMentions: Array<{
    platform: 'twitter' | 'reddit' | 'stocktwits' | 'other';
    text: string;
    author?: string;
    timestamp: string;
    engagement?: number;
  }>
): Promise<SentimentScore[] | null> {
  if (!socialMentions.length) return null;

  return socialMentions.map((mention) => {
    const text = mention.text.toLowerCase();
    const positiveHits = SOCIAL_POSITIVE_TERMS.filter((term) => text.includes(term));
    const negativeHits = SOCIAL_NEGATIVE_TERMS.filter((term) => text.includes(term));
    const rawScore = positiveHits.length - negativeHits.length;
    const engagementBoost = mention.engagement ? Math.min(Math.log10(mention.engagement + 1) / 10, 0.2) : 0;
    const score = Math.max(-1, Math.min(1, rawScore / 4 + Math.sign(rawScore) * engagementBoost));
    const sentiment = score > 0.15 ? 'positive' : score < -0.15 ? 'negative' : 'neutral';

    return {
      symbol,
      sentiment,
      score,
      confidence: Math.min(0.85, 0.45 + (positiveHits.length + negativeHits.length) * 0.12),
      source: 'social',
      analyzedText: mention.text,
      keyPhrases: [...positiveHits, ...negativeHits],
      timestamp: mention.timestamp,
    };
  });
}

/**
 * Obtiene analisis de sentimiento combinado (noticias + redes sociales si disponible)
 */
export async function getCombinedSentimentAnalysis(
  symbol: string,
  companyName: string,
  newsArticles: Array<{
    headline: string;
    summary?: string;
    datetime?: number;
    source?: string;
  }>,
  socialMentions?: Array<{
    platform: 'twitter' | 'reddit' | 'stocktwits' | 'other';
    text: string;
    author?: string;
    timestamp: string;
    engagement?: number;
  }>
): Promise<{
  news: NewsSentimentAnalysis | null;
  social: SentimentScore[] | null;
  combined: {
    overallSentiment: 'positive' | 'negative' | 'neutral';
    overallScore: number;
    newsScore: number;
    socialScore: number | null;
    confidence: number;
  } | null;
}> {
  const [newsSentiment, socialSentiment] = await Promise.all([
    analyzeNewsSentiment(symbol, companyName, newsArticles),
    socialMentions ? analyzeSocialSentiment(symbol, socialMentions) : Promise.resolve(null),
  ]);

  let combined = null;
  if (newsSentiment) {
    const socialScore = socialSentiment && socialSentiment.length > 0
      ? socialSentiment.reduce((sum, s) => sum + s.score, 0) / socialSentiment.length
      : null;

    // Ponderar: 70% noticias, 30% redes sociales (si disponible)
    const newsWeight = socialScore !== null ? 0.7 : 1.0;
    const socialWeight = socialScore !== null ? 0.3 : 0.0;

    const combinedScore = (newsSentiment.overallScore * newsWeight) +
      (socialScore !== null ? socialScore * socialWeight : 0);

    let overallSentiment: 'positive' | 'negative' | 'neutral';
    if (combinedScore > 0.2) {
      overallSentiment = 'positive';
    } else if (combinedScore < -0.2) {
      overallSentiment = 'negative';
    } else {
      overallSentiment = 'neutral';
    }

    const confidence = newsSentiment.articleCount > 5
      ? 0.8
      : newsSentiment.articleCount > 2
        ? 0.6
        : 0.4;

    combined = {
      overallSentiment,
      overallScore: combinedScore,
      newsScore: newsSentiment.overallScore,
      socialScore,
      confidence,
    };
  }

  return {
    news: newsSentiment,
    social: socialSentiment,
    combined,
  };
}



