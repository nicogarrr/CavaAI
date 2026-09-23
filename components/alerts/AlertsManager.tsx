'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Bell, History, Plus, RefreshCcw, Trash2 } from 'lucide-react';
import { createAlert, getUserAlerts, deleteAlert, type Alert, type CreateAlertInput, type AlertType } from '@/lib/actions/alerts.actions';
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
import { showErrorToast } from '@/lib/toast';
import { formatDate, formatDateTime } from '@/lib/format';
import { reviewResearchExpectations } from '@/lib/actions/research.actions';

const ALERT_TYPE_LABELS: Record<AlertType, string> = {
    price_above: 'Precio por encima de',
    price_below: 'Precio por debajo de',
    price_change: 'Cambio de precio %',
    news: 'Nueva noticia',
    earnings: 'Reporte de ganancias',
};

const isAlertType = (value: string | null | undefined): value is AlertType =>
    value === 'price_above' || value === 'price_below' || value === 'price_change' || value === 'news' || value === 'earnings';

function AlertsManager() {
    const searchParams = useSearchParams();
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [reviewing, setReviewing] = useState<string | null>(null);
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
        // Deep-link desde QuickAlertButton: /alerts?symbol=MSFT&type=price_below&value=300
        // pre-rellena el diálogo de creación y lo abre directamente.
        const symbol = searchParams.get('symbol');
        if (symbol) {
            const type = searchParams.get('type');
            const value = searchParams.get('value') ?? '';
            setFormData({
                symbol: symbol.toUpperCase(),
                type: isAlertType(type) ? type : 'price_above',
                condition: {
                    operator: type === 'price_below' || type === 'price_change' ? '<' : '>',
                    value,
                },
            });
            setOpen(true);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const loadAlerts = async () => {
        try {
            const data = await getUserAlerts();
            setAlerts(data);
        } catch (error) {
            showErrorToast(error, { onRetry: loadAlerts });
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
            showErrorToast(error, {
                duplicateMessage: 'Ya tienes esta alerta configurada.',
                onRetry: handleCreateAlert,
            });
        }
    };

    const handleDeleteAlert = async (alertId: string) => {
        try {
            await deleteAlert(alertId);
            await loadAlerts();
            toast.success('Alerta eliminada');
        } catch (error) {
            showErrorToast(error, {
                onRetry: () => handleDeleteAlert(alertId),
            });
        }
    };

    /**
     * Revisión de expectativas vs realidad para el ticker de la alerta:
     * dispara reviewResearchExpectations (POST expectation-reality/review)
     * para contrastar lo prometido con los hechos canónicos.
     */
    const handleReview = async (alert: Alert) => {
        if (!alert.symbol || reviewing) return;
        setReviewing(alert._id);
        try {
            await reviewResearchExpectations(alert.symbol);
            toast.success(`Revisión de expectativas lanzada para ${alert.symbol}`);
        } catch (error) {
            showErrorToast(error, {
                onRetry: () => handleReview(alert),
            });
        } finally {
            setReviewing(null);
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
                                    onValueChange={(value: AlertType) => setFormData({ ...formData, type: value })}
                                >
                                    <SelectTrigger className="bg-gray-900 border-gray-600 text-gray-100 h-11 text-base sm:h-9 sm:text-sm">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="bg-gray-900 border-gray-600">
                                        {Object.entries(ALERT_TYPE_LABELS).map(([value, label]) => (
                                            <SelectItem key={value} value={value}>{label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            {(formData.type === 'price_above' || formData.type === 'price_below' || formData.type === 'price_change') && (
                                <>
                                    <div>
                                        <Label htmlFor="operator" className="text-gray-300">Operador</Label>
                                        <Select
                                            value={formData.condition.operator}
                                            onValueChange={(value: CreateAlertInput['condition']['operator']) =>
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
                    <Button
                        size="sm"
                        variant="outline"
                        className="mt-4 min-h-[44px] px-4 sm:min-h-0"
                        onClick={() => setOpen(true)}
                    >
                        <Plus className="h-4 w-4" />
                        Crear la primera alerta
                    </Button>
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
                                        Creada: {formatDate(alert.createdAt)}
                                    </p>
                                    <p className={`inline-flex items-center gap-1 text-xs ${alert.lastTriggered ? 'text-amber-300' : 'text-gray-600'}`}>
                                        <History className="h-3.5 w-3.5" />
                                        {alert.lastTriggered
                                            ? `Disparada por última vez: ${formatDateTime(alert.lastTriggered)}`
                                            : 'Todavía no se ha disparado'}
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
                                {alert.symbol ? (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => handleReview(alert)}
                                        disabled={reviewing === alert._id}
                                        aria-label={`Revisar expectativas de ${alert.symbol}`}
                                        className="min-h-[44px] gap-1.5 px-3 text-xs sm:min-h-0"
                                    >
                                        <RefreshCcw className={`h-3.5 w-3.5 ${reviewing === alert._id ? 'animate-spin' : ''}`} />
                                        Revisar
                                    </Button>
                                ) : null}
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

/**
 * `useSearchParams` exige Suspense en el árbol del cliente; el contenido real
 * vive en AlertsManager y aquí se envuelve para cumplir el contrato de Next.
 */
export default function AlertsManagerWithSuspense() {
    return (
        <Suspense fallback={<div className="py-8 text-center text-gray-500">Cargando alertas...</div>}>
            <AlertsManager />
        </Suspense>
    );
}
