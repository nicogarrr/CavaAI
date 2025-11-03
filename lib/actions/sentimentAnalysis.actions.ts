'use server';

/**
 * Análisis de sentimiento de noticias y menciones
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
  summary?: string
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

RESPONDE EN FORMATO JSON EXACTO:
{
  "sentiment": "positive" | "negative" | "neutral",
  "score": número entre -1 y 1 (1 = muy positivo, -1 = muy negativo),
  "confidence": número entre 0 y 1 (qué tan seguro estás),
  "keyPhrases": ["frase1", "frase2"] (frases clave que influyeron en el sentimiento)
}

IMPORTANTE:
- Sé objetivo e imparcial
- Analiza SOLO el texto proporcionado
- NO uses información externa
- El sentimiento debe reflejar cómo afecta esto a ${symbol}`;

    const payload = {
      contents: [{
        role: 'user',
        parts: [{ text: prompt }],
      }],
    };

    const model = 'gemini-2.5-flash';
    const endpoint = `https://generativelanguage.googleapis.com/v1/models/${model}:generateContent?key=${apiKey}`;
    
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
    const text = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    
    if (!text) return null;

    // Extraer JSON de la respuesta
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return null;

    const result = JSON.parse(jsonMatch[0]);
    
    return {
      symbol,
      sentiment: result.sentiment || 'neutral',
      score: result.score || 0,
      confidence: result.confidence || 0.5,
      source: 'news',
      analyzedText: text,
      keyPhrases: result.keyPhrases || [],
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    console.error('Error analyzing news sentiment:', error);
    return null;
  }
}

/**
 * Analiza el sentimiento de múltiples noticias de una empresa
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
    // Analizar las últimas 10 noticias más relevantes
    const articlesToAnalyze = newsArticles.slice(0, 10);
    const sentimentScores: SentimentScore[] = [];

    // Analizar cada noticia (con límite de rate para no sobrecargar API)
    for (const article of articlesToAnalyze) {
      const sentiment = await analyzeNewsSentimentWithAI(
        symbol,
        article.headline,
        article.summary
      );
      
      if (sentiment) {
        sentimentScores.push(sentiment);
      }

      // Pequeña pausa para evitar rate limiting
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

    // Extraer frases clave de todos los análisis
    const allKeyPhrases = sentimentScores
      .flatMap(s => s.keyPhrases || [])
      .filter((phrase, index, arr) => arr.indexOf(phrase) === index)
      .slice(0, 5);

    // Formatear artículos analizados
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
 * Analiza sentimiento de menciones en redes sociales (placeholder)
 * Para implementación completa, se necesitaría:
 * - API de Twitter/X
 * - API de Reddit
 * - API de StockTwits
 * - Procesamiento de datos de redes sociales
 */
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
  // Por ahora, retornamos null ya que requiere integraciones con APIs de redes sociales
  // Esto se puede expandir cuando se tengan APIs configuradas
  return null;
}

/**
 * Obtiene análisis de sentimiento combinado (noticias + redes sociales si disponible)
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

