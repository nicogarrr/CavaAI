'use server';

/**
 * Datos macroeconómicos de Fed, BCE y otros bancos centrales
 * Fuentes: FRED (Federal Reserve Economic Data), ECB, Trading Economics
 */

export interface MacroData {
  source: 'fed' | 'ecb' | 'other';
  indicator: string;
  name: string;
  value: number;
  unit: string;
  date: string;
  change?: number;
  changePercent?: number;
  previousValue?: number;
}

export interface InterestRateData {
  fed: {
    current: number;
    previous: number;
    change: number;
    lastUpdated: string;
    nextMeeting?: string;
  } | null;
  ecb: {
    current: number;
    previous: number;
    change: number;
    lastUpdated: string;
    nextMeeting?: string;
  } | null;
  boj?: {
    current: number;
    previous: number;
    change: number;
    lastUpdated: string;
  } | null;
}

/**
 * Obtiene datos macroeconómicos del Fed (Federal Reserve)
 * Usa FRED API (Federal Reserve Economic Data)
 */
export async function getFedMacroData(): Promise<MacroData[]> {
  try {
    const fredApiKey = process.env.FRED_API_KEY;
    if (!fredApiKey) {
      console.warn('FRED API key no configurada');
      return [];
    }

    const indicators = [
      { series: 'DFF', name: 'Fed Funds Rate', unit: '%' },
      { series: 'UNRATE', name: 'Unemployment Rate', unit: '%' },
      { series: 'CPIAUCSL', name: 'CPI (Consumer Price Index)', unit: 'Index' },
      { series: 'GDP', name: 'GDP', unit: 'Billions USD' },
      { series: 'DGS10', name: '10-Year Treasury Rate', unit: '%' },
      { series: 'DGS2', name: '2-Year Treasury Rate', unit: '%' },
    ];

    const results: MacroData[] = [];

    for (const indicator of indicators) {
      try {
        const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${indicator.series}&api_key=${fredApiKey}&file_type=json&sort_order=desc&limit=2`;
        const response = await fetch(url, { next: { revalidate: 3600 } });
        
        if (!response.ok) continue;

        const data = await response.json();
        const observations = data?.observations || [];

        if (observations.length === 0) continue;

        const current = observations[0];
        const previous = observations[1] || current;

        const currentValue = parseFloat(current.value || '0');
        const previousValue = parseFloat(previous.value || '0');

        results.push({
          source: 'fed',
          indicator: indicator.series,
          name: indicator.name,
          value: currentValue,
          unit: indicator.unit,
          date: current.date || new Date().toISOString(),
          change: currentValue - previousValue,
          changePercent: previousValue !== 0 ? ((currentValue - previousValue) / previousValue) * 100 : 0,
          previousValue,
        });
      } catch (error) {
        console.warn(`Error fetching ${indicator.name} from FRED:`, error);
      }
    }

    return results;
  } catch (error) {
    console.error('Error fetching Fed macro data:', error);
    return [];
  }
}

/**
 * Obtiene tasas de interés del Fed y ECB
 * Usa APIs públicas y web scraping si es necesario
 */
export async function getInterestRates(): Promise<InterestRateData> {
  const result: InterestRateData = {
    fed: null,
    ecb: null,
  };

  try {
    // Fed Funds Rate usando FRED
    const fredApiKey = process.env.FRED_API_KEY;
    if (fredApiKey) {
      try {
        const url = `https://api.stlouisfed.org/fred/series/observations?series_id=DFF&api_key=${fredApiKey}&file_type=json&sort_order=desc&limit=2`;
        const response = await fetch(url, { next: { revalidate: 3600 } });
        
        if (response.ok) {
          const data = await response.json();
          const observations = data?.observations || [];
          
          if (observations.length > 0) {
            const current = parseFloat(observations[0].value || '0');
            const previous = observations.length > 1 ? parseFloat(observations[1].value || '0') : current;
            
            result.fed = {
              current,
              previous,
              change: current - previous,
              lastUpdated: observations[0].date || new Date().toISOString(),
            };
          }
        }
      } catch (error) {
        console.warn('Error fetching Fed rates:', error);
      }
    }

    // ECB rate usando Trading Economics API o web scraping
    try {
      // Intentar obtener desde API pública o usar datos conocidos
      // Nota: Esto requeriría una API key de Trading Economics o scraping
      const teApiKey = process.env.TRADING_ECONOMICS_API_KEY;
      if (teApiKey) {
        const url = `https://api.tradingeconomics.com/ecb?c=${teApiKey}`;
        const response = await fetch(url, { next: { revalidate: 3600 } });
        
        if (response.ok) {
          const data = await response.json();
          // Procesar datos de ECB según formato de la API
          // Esto depende de la estructura de la respuesta de Trading Economics
        }
      }
    } catch (error) {
      console.warn('Error fetching ECB rates:', error);
    }
  } catch (error) {
    console.error('Error fetching interest rates:', error);
  }

  return result;
}

/**
 * Obtiene datos macroeconómicos del BCE (European Central Bank)
 * Usa API del BCE o alternativas
 */
export async function getECBMacroData(): Promise<MacroData[]> {
  try {
    // El BCE tiene una API SDW (Statistical Data Warehouse)
    // Es compleja, así que usamos una aproximación alternativa
    const results: MacroData[] = [];

    // Para implementación completa, se necesitaría:
    // 1. API key de Trading Economics, o
    // 2. Implementar web scraping del sitio del BCE, o
    // 3. Usar otra fuente de datos macroeconómicos

    // Por ahora, retornamos estructura vacía que se puede expandir
    return results;
  } catch (error) {
    console.error('Error fetching ECB macro data:', error);
    return [];
  }
}

/**
 * Obtiene todos los datos macroeconómicos disponibles
 */
export async function getAllMacroData(): Promise<{
  fed: MacroData[];
  ecb: MacroData[];
  interestRates: InterestRateData;
}> {
  const [fedData, ecbData, interestRates] = await Promise.all([
    getFedMacroData(),
    getECBMacroData(),
    getInterestRates(),
  ]);

  return {
    fed: fedData,
    ecb: ecbData,
    interestRates,
  };
}

