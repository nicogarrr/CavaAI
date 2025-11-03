export const NAV_ITEMS = [
    { href: '/', label: 'Dashboard' },
    { href: '/search', label: 'Search' },
    { href: '/screener', label: 'Screener' },
    // { href: '/watchlist', label: 'Watchlist' },
];

// Sign-up form select options
export const INVESTMENT_GOALS = [
    { value: 'Growth', label: 'Growth' },
    { value: 'Income', label: 'Income' },
    { value: 'Balanced', label: 'Balanced' },
    { value: 'Conservative', label: 'Conservative' },
];

export const RISK_TOLERANCE_OPTIONS = [
    { value: 'Low', label: 'Low' },
    { value: 'Medium', label: 'Medium' },
    { value: 'High', label: 'High' },
];

export const PREFERRED_INDUSTRIES = [
    { value: 'Technology', label: 'Technology' },
    { value: 'Healthcare', label: 'Healthcare' },
    { value: 'Finance', label: 'Finance' },
    { value: 'Energy', label: 'Energy' },
    { value: 'Consumer Goods', label: 'Consumer Goods' },
];

export const ALERT_TYPE_OPTIONS = [
    { value: 'upper', label: 'Upper' },
    { value: 'lower', label: 'Lower' },
];

export const CONDITION_OPTIONS = [
    { value: 'greater', label: 'Greater than (>)' },
    { value: 'less', label: 'Less than (<)' },
];

// TradingView Charts
export const MARKET_OVERVIEW_WIDGET_CONFIG = {
    colorTheme: 'dark',
    dateRange: '12M',
    locale: 'en',
    largeChartUrl: '',
    isTransparent: true,
    showFloatingTooltip: true,
    plotLineColorGrowing: '#0FEDBE',
    plotLineColorFalling: '#0FEDBE',
    gridLineColor: 'rgba(240, 243, 250, 0)',
    scaleFontColor: '#DBDBDB',
    belowLineFillColorGrowing: 'rgba(41, 98, 255, 0.12)',
    belowLineFillColorFalling: 'rgba(41, 98, 255, 0.12)',
    belowLineFillColorGrowingBottom: 'rgba(41, 98, 255, 0)',
    belowLineFillColorFallingBottom: 'rgba(41, 98, 255, 0)',
    symbolActiveColor: 'rgba(15, 237, 190, 0.05)',
    tabs: [
        {
            title: 'Mi Cartera',
            symbols: [
                { s: 'AMEX:SPY', d: 'S&P 500 ETF' },
                { s: 'AMEX:URTH', d: 'MSCI World ETF' },
                { s: 'AMEX:VWO', d: 'Emerging Markets ETF' },
                { s: 'AMEX:BITO', d: 'Bitcoin Strategy ETF' },
                { s: 'AMEX:GLD', d: 'Gold ETF' },
                { s: 'NASDAQ:PYPL', d: 'PayPal' },
            ],
        },
        {
            title: 'Tech & Chips',
            symbols: [
                { s: 'NASDAQ:NVDA', d: 'NVIDIA' },
                { s: 'NASDAQ:AMD', d: 'AMD' },
                { s: 'NASDAQ:AAPL', d: 'Apple' },
                { s: 'NASDAQ:MSFT', d: 'Microsoft' },
                { s: 'NASDAQ:GOOGL', d: 'Alphabet' },
                { s: 'NASDAQ:META', d: 'Meta' },
            ],
        },
        {
            title: 'ETFs Globales',
            symbols: [
                { s: 'AMEX:VT', d: 'Total World Stock' },
                { s: 'AMEX:ACWI', d: 'MSCI ACWI' },
                { s: 'AMEX:VSS', d: 'Small-Cap ex-US' },
                { s: 'AMEX:EEM', d: 'Emerging Markets' },
                { s: 'NASDAQ:QQQ', d: 'NASDAQ-100' },
                { s: 'AMEX:VOO', d: 'S&P 500' },
            ],
        },
    ],
    support_host: 'https://www.tradingview.com',
    backgroundColor: '#141414',
    width: '100%',
    height: 600,
    showSymbolLogo: true,
    showChart: true,
};

export const HEATMAP_WIDGET_CONFIG = {
    dataSource: 'WORLD',
    blockSize: 'market_cap_basic',
    blockColor: 'change',
    grouping: 'sector',
    isTransparent: true,
    locale: 'en',
    symbolUrl: '',
    colorTheme: 'dark',
    exchanges: [],
    hasTopBar: false,
    isDataSetEnabled: false,
    isZoomEnabled: true,
    hasSymbolTooltip: true,
    isMonoSize: false,
    width: '100%',
    height: '600',
};

export const TOP_STORIES_WIDGET_CONFIG = {
    displayMode: 'regular',
    feedMode: 'symbol',
    colorTheme: 'dark',
    isTransparent: true,
    locale: 'en',
    market: 'stock',
    symbol: 'AMEX:SPY',
    // Símbolos adicionales para noticias personalizadas
    symbols: [
        ['AMEX:SPY', 'S&P 500'],
        ['AMEX:URTH', 'MSCI World'],
        ['AMEX:VWO', 'Emerging Markets'],
        ['AMEX:BITO', 'Bitcoin ETF'],
        ['AMEX:GLD', 'Gold'],
        ['NASDAQ:PYPL', 'PayPal'],
        ['NASDAQ:NVDA', 'NVIDIA'],
        ['NASDAQ:AMD', 'AMD'],
    ],
    width: '100%',
    height: '600',
};

// Símbolos para noticias personalizadas (sin prefijo de exchange)
// Limitado a 3 símbolos para evitar rate limiting de la API
export const NEWS_SYMBOLS = [
    'AAPL',     // Apple (más popular, mejor cobertura)
    'NVDA',     // NVIDIA (tecnología)
    'MSFT',     // Microsoft (tecnología)
    // Reducido de 10 a 3 para evitar límites de API
];

export const MARKET_DATA_WIDGET_CONFIG = {
    title: 'Mi Seguimiento',
    width: '100%',
    height: 600,
    locale: 'en',
    showSymbolLogo: true,
    colorTheme: 'dark',
    isTransparent: false,
    backgroundColor: '#0F0F0F',
    symbolsGroups: [
        {
            name: 'Índices & ETFs',
            symbols: [
                { name: 'AMEX:SPY', displayName: 'S&P 500' },
                { name: 'AMEX:URTH', displayName: 'MSCI World' },
                { name: 'AMEX:VWO', displayName: 'Emerging Markets' },
                { name: 'AMEX:VSS', displayName: 'Small-Cap Global' },
                { name: 'NASDAQ:QQQ', displayName: 'NASDAQ-100' },
                { name: 'AMEX:VOO', displayName: 'S&P 500 Vanguard' },
            ],
        },
        {
            name: 'Crypto & Oro',
            symbols: [
                { name: 'AMEX:BITO', displayName: 'Bitcoin Strategy ETF' },
                { name: 'AMEX:GLD', displayName: 'Gold ETF' },
                { name: 'NASDAQ:COIN', displayName: 'Coinbase' },
                { name: 'NASDAQ:MARA', displayName: 'Marathon Digital' },
                { name: 'AMEX:SLV', displayName: 'Silver ETF' },
                { name: 'AMEX:IAU', displayName: 'iShares Gold' },
            ],
        },
        {
            name: 'Tech Favoritos',
            symbols: [
                { name: 'NASDAQ:NVDA', displayName: 'NVIDIA' },
                { name: 'NASDAQ:AMD', displayName: 'AMD' },
                { name: 'NASDAQ:PYPL', displayName: 'PayPal' },
                { name: 'NASDAQ:AAPL', displayName: 'Apple' },
                { name: 'NASDAQ:MSFT', displayName: 'Microsoft' },
                { name: 'NASDAQ:GOOGL', displayName: 'Alphabet' },
            ],
        },
    ],
};

export const SYMBOL_INFO_WIDGET_CONFIG = (symbol: string) => ({
    symbol: symbol.toUpperCase(),
    colorTheme: 'dark',
    isTransparent: true,
    locale: 'en',
    width: '100%',
    height: 170,
});

export const CANDLE_CHART_WIDGET_CONFIG = (symbol: string) => ({
    allow_symbol_change: false,
    calendar: false,
    details: true,
    hide_side_toolbar: true,
    hide_top_toolbar: false,
    hide_legend: false,
    hide_volume: false,
    hotlist: false,
    interval: 'D',
    locale: 'en',
    save_image: false,
    style: 1,
    symbol: symbol.toUpperCase(),
    theme: 'dark',
    timezone: 'Etc/UTC',
    backgroundColor: '#141414',
    gridColor: '#141414',
    watchlist: [],
    withdateranges: false,
    compareSymbols: [],
    studies: [],
    width: '100%',
    height: 600,
});

export const BASELINE_WIDGET_CONFIG = (symbol: string) => ({
    allow_symbol_change: false,
    calendar: false,
    details: false,
    hide_side_toolbar: true,
    hide_top_toolbar: false,
    hide_legend: false,
    hide_volume: false,
    hotlist: false,
    interval: 'D',
    locale: 'en',
    save_image: false,
    style: 10,
    symbol: symbol.toUpperCase(),
    theme: 'dark',
    timezone: 'Etc/UTC',
    backgroundColor: '#141414',
    gridColor: '#141414',
    watchlist: [],
    withdateranges: false,
    compareSymbols: [],
    studies: [],
    width: '100%',
    height: 600,
});

export const TECHNICAL_ANALYSIS_WIDGET_CONFIG = (symbol: string) => ({
    symbol: symbol.toUpperCase(),
    colorTheme: 'dark',
    isTransparent: 'true',
    locale: 'en',
    width: '100%',
    height: 400,
    interval: '1h',
    largeChartUrl: '',
});

export const COMPANY_PROFILE_WIDGET_CONFIG = (symbol: string) => ({
    symbol: symbol.toUpperCase(),
    colorTheme: 'dark',
    isTransparent: 'true',
    locale: 'en',
    width: '100%',
    height: 440,
});

export const COMPANY_FINANCIALS_WIDGET_CONFIG = (symbol: string) => ({
    symbol: symbol.toUpperCase(),
    colorTheme: 'dark',
    isTransparent: 'true',
    locale: 'en',
    width: '100%',
    height: 464,
    displayMode: 'regular',
    largeChartUrl: '',
});

export const POPULAR_STOCK_SYMBOLS = [
    // Tech Giants (the big technology companies)
    'AAPL',
    'MSFT',
    'GOOGL',
    'AMZN',
    'TSLA',
    'META',
    'NVDA',
    'NFLX',
    'ORCL',
    'CRM',

    // Growing Tech Companies
    'ADBE',
    'INTC',
    'AMD',
    'PYPL',
    'UBER',
    'ZOOM',
    'SPOT',
    'SQ',
    'SHOP',
    'ROKU',

    // Newer Tech Companies
    'SNOW',
    'PLTR',
    'COIN',
    'RBLX',
    'DDOG',
    'CRWD',
    'NET',
    'OKTA',
    'TWLO',
    'ZM',

    // Consumer & Delivery Apps
    'DOCU',
    'PTON',
    'PINS',
    'SNAP',
    'LYFT',
    'DASH',
    'ABNB',
    'RIVN',
    'LCID',
    'NIO',

    // International Companies
    'XPEV',
    'LI',
    'BABA',
    'JD',
    'PDD',
    'TME',
    'BILI',
    'DIDI',
    'GRAB',
    'SE',
];

export const NO_MARKET_NEWS =
    '<p class="mobile-text" style="margin:0 0 20px 0;font-size:16px;line-height:1.6;color:#4b5563;">No market news available today. Please check back tomorrow.</p>';

export const WATCHLIST_TABLE_HEADER = [
    'Company',
    'Symbol',
    'Price',
    'Change',
    'Market Cap',
    'P/E Ratio',
    'Alert',
    'Action',
];