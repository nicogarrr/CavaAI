"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TrendingUp, TrendingDown, Activity, ArrowRight } from 'lucide-react'
import { getMarketMovers } from '@/lib/actions/fmp.actions'
import Link from 'next/link'

interface Mover {
    symbol: string
    name: string
    price: number
    changesPercentage: number
}

export function MarketMovers() {
    const [activeTab, setActiveTab] = useState('gainers')
    const [data, setData] = useState<Mover[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true)
            try {
                const movers = await getMarketMovers(activeTab as 'gainers' | 'losers' | 'active')
                // The API returns distinct keys based on type (gainers, losers, actives)
                // We need to handle this based on how the server action returns data
                // Our server action already unwraps the response: return type === 'gainers' ? data.gainers : ...
                setData(movers || [])
            } catch (error) {
                console.error('Error loading market movers', error)
            } finally {
                setLoading(false)
            }
        }

        fetchData()
    }, [activeTab])

    const renderList = (items: Mover[]) => (
        <div className="space-y-3">
            {items.slice(0, 5).map((stock) => (
                <Link
                    href={`/stocks/${stock.symbol}`}
                    key={stock.symbol}
                    className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors group"
                >
                    <div className="flex items-center gap-3">
                        <div className={`
              w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs
              ${stock.changesPercentage >= 0
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}
            `}>
                            {stock.symbol.substring(0, 2)}
                        </div>
                        <div>
                            <p className="font-semibold text-sm group-hover:text-primary transition-colors">{stock.symbol}</p>
                            <p className="text-xs text-muted-foreground truncate max-w-[120px]">{stock.name}</p>
                        </div>
                    </div>
                    <div className="text-right">
                        <p className="font-medium text-sm">${stock.price.toFixed(2)}</p>
                        <p className={`text-xs font-medium flex items-center justify-end
              ${stock.changesPercentage >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}
            `}>
                            {stock.changesPercentage >= 0 ? '+' : ''}{stock.changesPercentage.toFixed(2)}%
                        </p>
                    </div>
                </Link>
            ))}
        </div>
    )

    return (
        <Card className="h-full">
            <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                    <Activity className="h-5 w-5 text-primary" />
                    Market Movers
                </CardTitle>
            </CardHeader>
            <CardContent>
                <Tabs defaultValue="gainers" onValueChange={setActiveTab} className="w-full">
                    <TabsList className="grid w-full grid-cols-3 mb-4">
                        <TabsTrigger value="gainers" className="text-xs">
                            <TrendingUp className="h-3 w-3 mr-1" /> Ganadores
                        </TabsTrigger>
                        <TabsTrigger value="losers" className="text-xs">
                            <TrendingDown className="h-3 w-3 mr-1" /> Perdedores
                        </TabsTrigger>
                        <TabsTrigger value="active" className="text-xs">
                            <Activity className="h-3 w-3 mr-1" /> Activos
                        </TabsTrigger>
                    </TabsList>

                    <div className="min-h-[300px]">
                        {loading ? (
                            <div className="flex justify-center items-center h-[200px] text-muted-foreground text-sm">
                                Cargando datos...
                            </div>
                        ) : (
                            <>
                                <TabsContent value="gainers" className="mt-0 animate-in fade-in-50">
                                    {renderList(data)}
                                </TabsContent>
                                <TabsContent value="losers" className="mt-0 animate-in fade-in-50">
                                    {renderList(data)}
                                </TabsContent>
                                <TabsContent value="active" className="mt-0 animate-in fade-in-50">
                                    {renderList(data)}
                                </TabsContent>
                            </>
                        )}
                    </div>
                </Tabs>
            </CardContent>
        </Card>
    )
}
