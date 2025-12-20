'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
    AlertTriangle,
    Shield,
    TrendingUp,
    Calendar,
    DollarSign,
    AlertCircle,
    CheckCircle,
    Info,
    Loader2,
    RefreshCw,
    Zap,
    Target
} from 'lucide-react';
import {
    generateRedFlagsAnalysis,
    generateCatalystTimeline,
    type RedFlagsAnalysis,
    type CatalystTimeline,
    type RedFlag,
    type Catalyst
} from '@/lib/actions/ai.actions';
import { getOwnerEarnings } from '@/lib/actions/fmp.actions';
import { getStockHealthScore } from '@/lib/actions/healthScore.actions';

interface DeepAnalysisSectionProps {
    symbol: string;
    companyName: string;
    financialData: any;
    currentPrice: number;
}

type TabType = 'quality' | 'redflags' | 'catalysts' | 'owner';

export default function DeepAnalysisSection({
    symbol,
    companyName,
    financialData,
    currentPrice
}: DeepAnalysisSectionProps) {
    const [activeTab, setActiveTab] = useState<TabType>('quality');
    const [loading, setLoading] = useState(true);

    // Data states
    const [healthScore, setHealthScore] = useState<any>(null);
    const [redFlags, setRedFlags] = useState<RedFlagsAnalysis | null>(null);
    const [catalysts, setCatalysts] = useState<CatalystTimeline | null>(null);
    const [ownerEarnings, setOwnerEarnings] = useState<any>(null);

    // Load data based on active tab
    useEffect(() => {
        loadTabData(activeTab);
    }, [activeTab, symbol]);

    const loadTabData = async (tab: TabType) => {
        setLoading(true);
        try {
            switch (tab) {
                case 'quality':
                    if (!healthScore) {
                        const data = await getStockHealthScore(symbol);
                        setHealthScore(data);
                    }
                    break;
                case 'redflags':
                    if (!redFlags) {
                        const data = await generateRedFlagsAnalysis({
                            symbol,
                            companyName,
                            financialData,
                            currentPrice
                        });
                        setRedFlags(data);
                    }
                    break;
                case 'catalysts':
                    if (!catalysts) {
                        const data = await generateCatalystTimeline({
                            symbol,
                            companyName,
                            financialData,
                            currentPrice
                        });
                        setCatalysts(data);
                    }
                    break;
                case 'owner':
                    if (!ownerEarnings) {
                        const data = await getOwnerEarnings(symbol);
                        setOwnerEarnings(data);
                    }
                    break;
            }
        } catch (error) {
            console.error(`Error loading ${tab} data:`, error);
        }
        setLoading(false);
    };

    const TABS = [
        { id: 'quality' as TabType, label: 'Quality Score', icon: <Shield className="h-4 w-4" /> },
        { id: 'redflags' as TabType, label: 'Red Flags', icon: <AlertTriangle className="h-4 w-4" /> },
        { id: 'catalysts' as TabType, label: 'Catalizadores', icon: <Calendar className="h-4 w-4" /> },
        { id: 'owner' as TabType, label: "Owner's Earnings", icon: <DollarSign className="h-4 w-4" /> },
    ];

    return (
        <div className="space-y-4">
            {/* Tab Navigation */}
            <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-1 flex gap-1">
                {TABS.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-md transition-all duration-200 ${activeTab === tab.id
                            ? 'bg-gradient-to-r from-purple-500/20 to-indigo-500/20 border border-purple-500/50 text-white'
                            : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
                            }`}
                    >
                        {tab.icon}
                        <span className="hidden sm:inline text-sm font-medium">{tab.label}</span>
                    </button>
                ))}
            </div>

            {/* Content Area */}
            <div className="min-h-[400px]">
                {loading ? (
                    <LoadingSkeleton />
                ) : (
                    <>
                        {activeTab === 'quality' && <QualityScorePanel data={healthScore} />}
                        {activeTab === 'redflags' && <RedFlagsPanel data={redFlags} />}
                        {activeTab === 'catalysts' && <CatalystsPanel data={catalysts} />}
                        {activeTab === 'owner' && <OwnerEarningsPanel data={ownerEarnings} currentPrice={currentPrice} />}
                    </>
                )}
            </div>
        </div>
    );
}

// ============================================
// QUALITY SCORE PANEL
// ============================================

function QualityScorePanel({ data }: { data: any }) {
    if (!data) {
        return <EmptyState message="No se pudieron cargar los datos del Quality Score" />;
    }

    const categories = [
        { key: 'profitability', label: 'Rentabilidad', icon: <TrendingUp className="h-4 w-4" />, color: 'from-green-500 to-emerald-500' },
        { key: 'growth', label: 'Crecimiento', icon: <Zap className="h-4 w-4" />, color: 'from-blue-500 to-cyan-500' },
        { key: 'stability', label: 'Estabilidad', icon: <Shield className="h-4 w-4" />, color: 'from-purple-500 to-violet-500' },
        { key: 'efficiency', label: 'Eficiencia', icon: <Target className="h-4 w-4" />, color: 'from-orange-500 to-amber-500' },
        { key: 'valuation', label: 'Valoración', icon: <DollarSign className="h-4 w-4" />, color: 'from-pink-500 to-rose-500' },
    ];

    const getScoreColor = (score: number) => {
        if (score >= 80) return 'text-green-400';
        if (score >= 60) return 'text-lime-400';
        if (score >= 40) return 'text-yellow-400';
        if (score >= 20) return 'text-orange-400';
        return 'text-red-400';
    };

    return (
        <Card className="p-6 bg-gray-800/50 border-gray-700">
            {/* Header with overall score */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-xl font-bold text-white">Quality Score</h3>
                    <p className="text-sm text-gray-400">Análisis multidimensional de calidad</p>
                </div>
                <div className="text-center">
                    <div className={`text-4xl font-bold ${getScoreColor(data.score)}`}>
                        {data.score}
                    </div>
                    <Badge className={`${data.grade?.startsWith('A') ? 'bg-green-600' : data.grade?.startsWith('B') ? 'bg-teal-600' : 'bg-yellow-600'}`}>
                        Grado {data.grade}
                    </Badge>
                </div>
            </div>

            {/* Category Breakdown */}
            <div className="grid gap-4">
                {categories.map((cat) => {
                    const score = data.breakdown?.[cat.key] || 0;
                    return (
                        <div key={cat.key} className="space-y-2">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <div className={`p-1.5 rounded bg-gradient-to-r ${cat.color} bg-opacity-20`}>
                                        {cat.icon}
                                    </div>
                                    <span className="text-sm font-medium text-gray-300">{cat.label}</span>
                                </div>
                                <span className={`text-sm font-bold ${getScoreColor(score)}`}>{score}/100</span>
                            </div>
                            <Progress value={score} className="h-2" />
                        </div>
                    );
                })}
            </div>

            {/* Strengths & Weaknesses */}
            {(data.strengths?.length > 0 || data.weaknesses?.length > 0) && (
                <div className="grid grid-cols-2 gap-4 mt-6">
                    {data.strengths?.length > 0 && (
                        <div className="p-3 bg-green-900/20 rounded-lg border border-green-900/30">
                            <h4 className="text-sm font-medium text-green-400 mb-2 flex items-center gap-1">
                                <CheckCircle className="h-4 w-4" /> Fortalezas
                            </h4>
                            <ul className="text-xs space-y-1 text-gray-300">
                                {data.strengths.slice(0, 3).map((s: string, i: number) => (
                                    <li key={i}>• {s}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {data.weaknesses?.length > 0 && (
                        <div className="p-3 bg-red-900/20 rounded-lg border border-red-900/30">
                            <h4 className="text-sm font-medium text-red-400 mb-2 flex items-center gap-1">
                                <AlertCircle className="h-4 w-4" /> Debilidades
                            </h4>
                            <ul className="text-xs space-y-1 text-gray-300">
                                {data.weaknesses.slice(0, 3).map((w: string, i: number) => (
                                    <li key={i}>• {w}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
}

// ============================================
// RED FLAGS PANEL
// ============================================

function RedFlagsPanel({ data }: { data: RedFlagsAnalysis | null }) {
    if (!data) {
        return <EmptyState message="No se pudo cargar el análisis de Red Flags" />;
    }

    const getSeverityIcon = (severity: RedFlag['severity']) => {
        switch (severity) {
            case 'critical': return <AlertCircle className="h-5 w-5 text-red-500" />;
            case 'warning': return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
            case 'info': return <Info className="h-5 w-5 text-blue-500" />;
        }
    };

    const getSeverityBg = (severity: RedFlag['severity']) => {
        switch (severity) {
            case 'critical': return 'bg-red-900/30 border-red-900/50';
            case 'warning': return 'bg-yellow-900/30 border-yellow-900/50';
            case 'info': return 'bg-blue-900/30 border-blue-900/50';
        }
    };

    const getRiskColor = (risk: string) => {
        switch (risk) {
            case 'critical': return 'bg-red-600';
            case 'high': return 'bg-orange-600';
            case 'medium': return 'bg-yellow-600';
            default: return 'bg-green-600';
        }
    };

    return (
        <Card className="p-6 bg-gray-800/50 border-gray-700">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-xl font-bold text-white flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-yellow-500" />
                        Red Flags Detector
                    </h3>
                    <p className="text-sm text-gray-400">{data.summary}</p>
                </div>
                <div className="text-center">
                    <div className="text-3xl font-bold text-white">{data.riskScore}</div>
                    <Badge className={getRiskColor(data.overallRisk)}>
                        Riesgo {data.overallRisk.toUpperCase()}
                    </Badge>
                </div>
            </div>

            {/* Flags List */}
            {data.flags.length === 0 ? (
                <div className="text-center py-8">
                    <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
                    <p className="text-green-400 font-medium">Sin Red Flags Detectados</p>
                    <p className="text-sm text-gray-400">La empresa no presenta señales de alarma significativas</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {data.flags.map((flag, index) => (
                        <div key={flag.id || index} className={`p-4 rounded-lg border ${getSeverityBg(flag.severity)}`}>
                            <div className="flex items-start gap-3">
                                {getSeverityIcon(flag.severity)}
                                <div className="flex-1">
                                    <div className="flex items-center justify-between">
                                        <h4 className="font-medium text-white">{flag.title}</h4>
                                        <Badge variant="outline" className="text-xs">{flag.category}</Badge>
                                    </div>
                                    <p className="text-sm text-gray-300 mt-1">{flag.description}</p>
                                    {flag.metric && (
                                        <div className="mt-2 flex items-center gap-2 text-xs">
                                            <span className="text-gray-500">{flag.metric}:</span>
                                            <span className="font-mono text-gray-300">{flag.value}</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}

// ============================================
// CATALYSTS PANEL
// ============================================

function CatalystsPanel({ data }: { data: CatalystTimeline | null }) {
    if (!data) {
        return <EmptyState message="No se pudo cargar el timeline de catalizadores" />;
    }

    const getTypeIcon = (type: Catalyst['type']) => {
        switch (type) {
            case 'earnings': return '📊';
            case 'dividend': return '💰';
            case 'conference': return '🎤';
            case 'product': return '🚀';
            case 'regulatory': return '⚖️';
            case 'ma': return '🤝';
            default: return '📅';
        }
    };

    const getImpactColor = (impact: Catalyst['impact']) => {
        switch (impact) {
            case 'positive': return 'text-green-400 bg-green-900/30';
            case 'negative': return 'text-red-400 bg-red-900/30';
            case 'neutral': return 'text-gray-400 bg-gray-900/30';
            default: return 'text-blue-400 bg-blue-900/30';
        }
    };

    const getImportanceBadge = (importance: Catalyst['importance']) => {
        switch (importance) {
            case 'high': return 'bg-red-600';
            case 'medium': return 'bg-yellow-600';
            default: return 'bg-gray-600';
        }
    };

    return (
        <Card className="p-6 bg-gray-800/50 border-gray-700">
            {/* Header */}
            <div className="mb-6">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                    <Calendar className="h-5 w-5 text-indigo-400" />
                    Catalyst Timeline
                </h3>
                <p className="text-sm text-gray-400">{data.summary}</p>
            </div>

            {/* Next Major Event */}
            {data.nextMajorEvent && (
                <div className="p-4 bg-gradient-to-r from-indigo-900/30 to-purple-900/30 rounded-lg border border-indigo-700/50 mb-6">
                    <div className="text-xs text-indigo-400 uppercase tracking-wider mb-1">Próximo Evento Importante</div>
                    <div className="flex items-center gap-3">
                        <span className="text-2xl">{getTypeIcon(data.nextMajorEvent.type)}</span>
                        <div className="flex-1">
                            <h4 className="font-bold text-white">{data.nextMajorEvent.title}</h4>
                            <p className="text-sm text-gray-300">{data.nextMajorEvent.description}</p>
                        </div>
                        <div className="text-right">
                            <div className="text-lg font-bold text-indigo-300">{data.nextMajorEvent.date}</div>
                            <Badge className={getImportanceBadge(data.nextMajorEvent.importance)}>
                                {data.nextMajorEvent.importance.toUpperCase()}
                            </Badge>
                        </div>
                    </div>
                </div>
            )}

            {/* Timeline */}
            {data.catalysts.length === 0 ? (
                <div className="text-center py-8">
                    <Calendar className="h-12 w-12 text-gray-500 mx-auto mb-3" />
                    <p className="text-gray-400">No se identificaron catalizadores próximos</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {data.catalysts.map((catalyst, index) => (
                        <div key={catalyst.id || index} className="flex items-start gap-3 p-3 bg-gray-900/50 rounded-lg">
                            <span className="text-xl">{getTypeIcon(catalyst.type)}</span>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h4 className="font-medium text-white">{catalyst.title}</h4>
                                    <Badge className={`text-xs ${getImpactColor(catalyst.impact)}`}>
                                        {catalyst.impact}
                                    </Badge>
                                </div>
                                <p className="text-sm text-gray-400 truncate">{catalyst.description}</p>
                            </div>
                            <div className="text-right shrink-0">
                                <div className="text-sm font-medium text-gray-300">{catalyst.date}</div>
                                <Badge variant="outline" className="text-xs mt-1">
                                    {catalyst.importance}
                                </Badge>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}

// ============================================
// OWNER'S EARNINGS PANEL
// ============================================

function OwnerEarningsPanel({ data, currentPrice }: { data: any; currentPrice: number }) {
    if (!data?.ownerEarnings?.[0]) {
        return <EmptyState message="No se pudieron cargar los Owner's Earnings" />;
    }

    const oe = data.ownerEarnings[0];
    const formatCurrency = (val: number) => {
        if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
        if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
        return `$${val.toFixed(2)}`;
    };

    // Calculate Owner's Earnings yield
    const oeYield = oe.ownersEarningsPerShare ? ((oe.ownersEarningsPerShare / currentPrice) * 100).toFixed(2) : 'N/A';
    const isGood = parseFloat(oeYield) > 5;

    return (
        <Card className="p-6 bg-gray-800/50 border-gray-700">
            {/* Header */}
            <div className="mb-6">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                    <DollarSign className="h-5 w-5 text-green-400" />
                    Owner's Earnings (Buffett)
                </h3>
                <p className="text-sm text-gray-400">
                    La métrica preferida de Warren Buffett para valorar empresas
                </p>
            </div>

            {/* Main Metric */}
            <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="p-4 bg-gradient-to-br from-green-900/30 to-emerald-900/30 rounded-xl border border-green-700/30">
                    <div className="text-xs text-green-400 uppercase tracking-wider mb-1">Owner's Earnings</div>
                    <div className="text-3xl font-bold text-green-400">{formatCurrency(oe.ownersEarnings)}</div>
                    <div className="text-sm text-gray-400 mt-1">
                        {oe.ownersEarningsPerShare?.toFixed(2)} $/acción
                    </div>
                </div>
                <div className={`p-4 rounded-xl border ${isGood ? 'bg-green-900/20 border-green-700/30' : 'bg-yellow-900/20 border-yellow-700/30'}`}>
                    <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">OE Yield</div>
                    <div className={`text-3xl font-bold ${isGood ? 'text-green-400' : 'text-yellow-400'}`}>
                        {oeYield}%
                    </div>
                    <div className="text-sm text-gray-400 mt-1">
                        {isGood ? 'Atractivo (>5%)' : 'Moderado'}
                    </div>
                </div>
            </div>

            {/* Breakdown */}
            <div className="p-4 bg-gray-900/50 rounded-lg">
                <h4 className="text-sm font-medium text-gray-300 mb-3">Desglose del Cálculo</h4>
                <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                        <span className="text-gray-400">Average PPE</span>
                        <span className="text-gray-300 font-mono">{formatCurrency(oe.averagePPE)}</span>
                    </div>
                    <div className="flex justify-between">
                        <span className="text-gray-400">Maintenance CapEx</span>
                        <span className="text-red-400 font-mono">-{formatCurrency(Math.abs(oe.maintenanceCapex))}</span>
                    </div>
                    <div className="flex justify-between">
                        <span className="text-gray-400">Growth CapEx</span>
                        <span className="text-blue-400 font-mono">{formatCurrency(oe.growthCapex)}</span>
                    </div>
                    <div className="border-t border-gray-700 pt-2 mt-2 flex justify-between font-medium">
                        <span className="text-white">Owner's Earnings</span>
                        <span className="text-green-400 font-mono">{formatCurrency(oe.ownersEarnings)}</span>
                    </div>
                </div>
            </div>

            {/* Formula explanation */}
            <div className="mt-4 p-3 bg-gray-900/30 rounded-lg text-xs text-gray-500">
                <p><strong>Fórmula:</strong> Net Income + D&A - Maintenance CapEx - ΔWorking Capital</p>
                <p className="mt-1">Los Owner's Earnings representan el efectivo real que el dueño podría extraer sin dañar el negocio.</p>
            </div>
        </Card>
    );
}

// ============================================
// HELPER COMPONENTS
// ============================================

function LoadingSkeleton() {
    return (
        <Card className="p-6 bg-gray-800/50 border-gray-700">
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
                <span className="ml-3 text-gray-400">Analizando datos...</span>
            </div>
        </Card>
    );
}

function EmptyState({ message }: { message: string }) {
    return (
        <Card className="p-6 bg-gray-800/50 border-gray-700">
            <div className="text-center py-8">
                <AlertCircle className="h-12 w-12 text-gray-500 mx-auto mb-3" />
                <p className="text-gray-400">{message}</p>
            </div>
        </Card>
    );
}
