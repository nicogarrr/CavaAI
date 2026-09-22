'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Bell, Plus, Trash2 } from 'lucide-react';
import { createAlert, getUserAlerts, deleteAlert, type Alert, type CreateAlertInput } from '@/lib/actions/alerts.actions';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { getFriendlyErrorMessage } from '@/lib/types/errors';

export default function AlertsManager() {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [formData, setFormData] = useState<CreateAlertInput>({
        symbol: '',
        type: 'price_above',
        condition: {
            operator: '>',
            value: '',
        },
    });

    useEffect(() => {
        loadAlerts();
    }, []);

    const loadAlerts = async () => {
        try {
            const data = await getUserAlerts();
            setAlerts(data);
        } catch (error) {
            toast.error(getFriendlyErrorMessage(error));
        } finally {
            setLoading(false);
        }
    };

    const handleCreateAlert = async () => {
        try {
            const numericValue = formData.type === 'news' || formData.type === 'earnings' 
                ? formData.condition.value 
                : parseFloat(String(formData.condition.value));
            
            if (isNaN(numericValue as number) && formData.type !== 'news' && formData.type !== 'earnings') {
                toast.error('Introduce un valor numérico válido');
                return;
            }

            await createAlert({
                ...formData,
                condition: {
                    ...formData.condition,
                    value: numericValue,
                },
            });
            toast.success('Alerta creada');
            
            setOpen(false);
            setFormData({
                symbol: '',
                type: 'price_above',
                condition: {
                    operator: '>',
                    value: '',
                },
            });
            loadAlerts();
        } catch (error) {
            toast.error(getFriendlyErrorMessage(error));
        }
    };

    const handleDeleteAlert = async (alertId: string) => {
        try {
            await deleteAlert(alertId);
            await loadAlerts();
            toast.success('Alerta eliminada');
        } catch (error) {
            toast.error(getFriendlyErrorMessage(error));
        }
    };

    const getAlertLabel = (alert: Alert) => {
        const symbol = alert.symbol;
        const type = alert.type;
        const operator = alert.condition.operator;
        const value = alert.condition.value;

        if (type === 'price_above') {
            return `${symbol}: Precio por encima de $${value}`;
        }
        if (type === 'price_below') {
            return `${symbol}: Precio por debajo de $${value}`;
        }
        if (type === 'price_change') {
            return `${symbol}: Cambio de precio ${operator === '>' ? 'mayor' : 'menor'} a ${value}%`;
        }
        if (type === 'news') {
            return `${symbol}: Nueva noticia`;
        }
        if (type === 'earnings') {
            return `${symbol}: Reporte de ganancias`;
        }
        return `${symbol}: Alerta`;
    };

    return (
        <Card className="p-4 sm:p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="flex flex-col gap-3 mb-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                    <Bell className="h-5 w-5 shrink-0 text-teal-400" />
                    <h2 className="text-lg sm:text-xl font-semibold text-gray-200">Alertas en Tiempo Real</h2>
                </div>
                <Dialog open={open} onOpenChange={setOpen}>
                    <DialogTrigger asChild>
                        <Button size="sm" className="gap-2 min-h-[44px] px-4 text-sm sm:min-h-0 sm:text-xs">
                            <Plus className="h-4 w-4" />
                            Nueva Alerta
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="bg-gray-800 border-gray-700 max-h-[90dvh] overflow-y-auto w-[calc(100vw-2rem)] sm:max-w-md">
                        <DialogHeader>
                            <DialogTitle className="text-gray-100">Crear Nueva Alerta</DialogTitle>
                            <DialogDescription className="text-gray-400">
                                Configura alertas para recibir notificaciones en tiempo real sobre cambios en tus acciones.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 mt-4">
                            <div>
                                <Label htmlFor="symbol" className="text-gray-300">Símbolo</Label>
                                <Input
                                    id="symbol"
                                    value={formData.symbol}
                                    onChange={(e) => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
                                    placeholder="AAPL"
                                    className="bg-gray-900 border-gray-600 text-gray-100 h-11 text-base sm:h-9 sm:text-sm"
                                />
                            </div>
                            <div>
                                <Label htmlFor="type" className="text-gray-300">Tipo de Alerta</Label>
                                <Select
                                    value={formData.type}
                                    onValueChange={(value: any) => setFormData({ ...formData, type: value })}
                                >
                                    <SelectTrigger className="bg-gray-900 border-gray-600 text-gray-100 h-11 text-base sm:h-9 sm:text-sm">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="bg-gray-900 border-gray-600">
                                        <SelectItem value="price_above">Precio por encima de</SelectItem>
                                        <SelectItem value="price_below">Precio por debajo de</SelectItem>
                                        <SelectItem value="price_change">Cambio de precio %</SelectItem>
                                        <SelectItem value="news">Nueva noticia</SelectItem>
                                        <SelectItem value="earnings">Reporte de ganancias</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            {(formData.type === 'price_above' || formData.type === 'price_below' || formData.type === 'price_change') && (
                                <>
                                    <div>
                                        <Label htmlFor="operator" className="text-gray-300">Operador</Label>
                                        <Select
                                            value={formData.condition.operator}
                                            onValueChange={(value: any) => 
                                                setFormData({ 
                                                    ...formData, 
                                                    condition: { ...formData.condition, operator: value } 
                                                })
                                            }
                                        >
                                            <SelectTrigger className="bg-gray-900 border-gray-600 text-gray-100 h-11 text-base sm:h-9 sm:text-sm">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent className="bg-gray-900 border-gray-600">
                                                <SelectItem value=">">Mayor que (&gt;)</SelectItem>
                                                <SelectItem value="<">Menor que (&lt;)</SelectItem>
                                                <SelectItem value=">=">Mayor o igual (&gt;=)</SelectItem>
                                                <SelectItem value="<=">Menor o igual (&lt;=)</SelectItem>
                                                <SelectItem value="==">Igual a (==)</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <Label htmlFor="value" className="text-gray-300">
                                            {formData.type === 'price_change' ? 'Porcentaje (%)' : 'Precio (USD)'}
                                        </Label>
                                        <Input
                                            id="value"
                                            type="number"
                                            value={formData.condition.value}
                                            onChange={(e) => 
                                                setFormData({ 
                                                    ...formData, 
                                                    condition: { ...formData.condition, value: e.target.value } 
                                                })
                                            }
                                            placeholder={formData.type === 'price_change' ? "5" : "100.00"}
                                            className="bg-gray-900 border-gray-600 text-gray-100 h-11 text-base sm:h-9 sm:text-sm"
                                        />
                                    </div>
                                </>
                            )}
                            <Button onClick={handleCreateAlert} className="w-full min-h-[44px] text-sm sm:text-xs">
                                Crear Alerta
                            </Button>
                        </div>
                    </DialogContent>
                </Dialog>
            </div>

            {loading ? (
                <div className="text-center py-8 text-gray-500">Cargando alertas...</div>
            ) : alerts.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                    <Bell className="h-12 w-12 mx-auto mb-3 text-gray-600" />
                    <p>No tienes alertas configuradas</p>
                    <p className="text-sm mt-2">Crea tu primera alerta para recibir notificaciones en tiempo real</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {alerts.map((alert) => (
                        <div
                            key={alert._id}
                            className="flex flex-col gap-3 p-4 bg-gray-900/50 rounded-lg border border-gray-700/50 sm:flex-row sm:items-center sm:justify-between"
                        >
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-gray-200 break-words">
                                    {getAlertLabel(alert)}
                                </p>
                                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                                    <p className="text-xs text-gray-500">
                                        Creada: {new Date(alert.createdAt).toLocaleDateString('es-ES')}
                                    </p>
                                    {alert.symbol ? (
                                        <Link
                                            href={`/research/${encodeURIComponent(alert.symbol)}`}
                                            className="inline-flex min-h-[44px] items-center px-2 py-2 text-xs text-teal-400 hover:text-teal-300 sm:min-h-0 sm:p-0"
                                        >
                                            Ver research →
                                        </Link>
                                    ) : null}
                                </div>
                            </div>
                            <div className="flex items-center justify-end gap-1">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleDeleteAlert(alert._id)}
                                    aria-label="Eliminar alerta"
                                    className="min-h-[44px] min-w-[44px] text-gray-400 hover:text-red-400"
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}

