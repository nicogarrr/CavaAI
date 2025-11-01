'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Bell, Plus, Trash2, X } from 'lucide-react';
import { createAlert, getUserAlerts, deleteAlert, type CreateAlertInput } from '@/lib/actions/alerts.actions';
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

export default function AlertsManager() {
    const [alerts, setAlerts] = useState<any[]>([]);
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
            console.error('Error loading alerts:', error);
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
                alert('Por favor ingresa un valor numérico válido');
                return;
            }

            await createAlert({
                ...formData,
                condition: {
                    ...formData.condition,
                    value: numericValue,
                },
            });
            
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
            console.error('Error creating alert:', error);
            alert('Error al crear la alerta');
        }
    };

    const handleDeleteAlert = async (alertId: string) => {
        try {
            await deleteAlert(alertId);
            loadAlerts();
        } catch (error) {
            console.error('Error deleting alert:', error);
        }
    };

    const getAlertLabel = (alert: any) => {
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
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    <Bell className="h-5 w-5 text-teal-400" />
                    <h2 className="text-xl font-semibold text-gray-200">Alertas en Tiempo Real</h2>
                </div>
                <Dialog open={open} onOpenChange={setOpen}>
                    <DialogTrigger asChild>
                        <Button size="sm" className="gap-2">
                            <Plus className="h-4 w-4" />
                            Nueva Alerta
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="bg-gray-800 border-gray-700">
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
                                    className="bg-gray-900 border-gray-600 text-gray-100"
                                />
                            </div>
                            <div>
                                <Label htmlFor="type" className="text-gray-300">Tipo de Alerta</Label>
                                <Select
                                    value={formData.type}
                                    onValueChange={(value: any) => setFormData({ ...formData, type: value })}
                                >
                                    <SelectTrigger className="bg-gray-900 border-gray-600 text-gray-100">
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
                                            <SelectTrigger className="bg-gray-900 border-gray-600 text-gray-100">
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
                                            className="bg-gray-900 border-gray-600 text-gray-100"
                                        />
                                    </div>
                                </>
                            )}
                            <Button onClick={handleCreateAlert} className="w-full">
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
                            className="flex items-center justify-between p-4 bg-gray-900/50 rounded-lg border border-gray-700/50"
                        >
                            <div className="flex-1">
                                <p className="text-sm font-medium text-gray-200">
                                    {getAlertLabel(alert)}
                                </p>
                                <p className="text-xs text-gray-500 mt-1">
                                    Creada: {new Date(alert.createdAt).toLocaleDateString('es-ES')}
                                </p>
                            </div>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteAlert(alert._id)}
                                className="text-gray-400 hover:text-red-400"
                            >
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}

