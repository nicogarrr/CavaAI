'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Pencil } from 'lucide-react';
import { updateTransaction } from '@/lib/actions/portfolio.actions';
import { useRouter } from 'next/navigation';

type Transaction = {
    _id: string;
    symbol: string;
    type: 'buy' | 'sell';
    quantity: number;
    price: number;
    date: string;
    notes?: string;
};

type Props = {
    transaction: Transaction;
    userId: string;
};

export default function EditTransactionDialog({ transaction, userId }: Props) {
    const router = useRouter();
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);

    const [formData, setFormData] = useState({
        symbol: transaction.symbol,
        type: transaction.type,
        quantity: transaction.quantity.toString(),
        price: transaction.price.toString(),
        date: new Date(transaction.date).toISOString().split('T')[0],
        notes: transaction.notes || '',
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);

        const result = await updateTransaction(
            userId,
            transaction._id,
            formData.symbol,
            formData.type,
            parseFloat(formData.quantity),
            parseFloat(formData.price),
            new Date(formData.date),
            formData.notes || undefined
        );

        setLoading(false);

        if (result.success) {
            setOpen(false);
            router.refresh();
        } else {
            alert('Error al actualizar la transacción');
        }
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button
                    variant="ghost"
                    size="icon"
                    className="text-blue-400 hover:text-blue-300 hover:bg-blue-950/20"
                >
                    <Pencil className="h-4 w-4" />
                </Button>
            </DialogTrigger>
            <DialogContent className="bg-gray-900 border-gray-700 max-w-md">
                <DialogHeader>
                    <DialogTitle className="text-gray-100">Editar Transacción</DialogTitle>
                    <DialogDescription className="text-gray-400">
                        Modifica los detalles de la transacción
                    </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label htmlFor="symbol" className="text-gray-300">Símbolo</Label>
                        <Input
                            id="symbol"
                            value={formData.symbol}
                            onChange={(e) => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
                            required
                            className="bg-gray-800 border-gray-700 text-gray-100"
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="type" className="text-gray-300">Tipo de Operación</Label>
                        <Select
                            value={formData.type}
                            onValueChange={(value: 'buy' | 'sell') => setFormData({ ...formData, type: value })}
                        >
                            <SelectTrigger className="bg-gray-800 border-gray-700 text-gray-100">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-gray-800 border-gray-700">
                                <SelectItem value="buy">🟢 Compra</SelectItem>
                                <SelectItem value="sell">🔴 Venta</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="quantity" className="text-gray-300">Cantidad</Label>
                            <Input
                                id="quantity"
                                type="number"
                                step="0.01"
                                min="0"
                                value={formData.quantity}
                                onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
                                required
                                className="bg-gray-800 border-gray-700 text-gray-100"
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="price" className="text-gray-300">Precio ($)</Label>
                            <Input
                                id="price"
                                type="number"
                                step="0.01"
                                min="0"
                                value={formData.price}
                                onChange={(e) => setFormData({ ...formData, price: e.target.value })}
                                required
                                className="bg-gray-800 border-gray-700 text-gray-100"
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="date" className="text-gray-300">Fecha</Label>
                        <Input
                            id="date"
                            type="date"
                            value={formData.date}
                            onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                            required
                            className="bg-gray-800 border-gray-700 text-gray-100"
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="notes" className="text-gray-300">Notas (opcional)</Label>
                        <Input
                            id="notes"
                            value={formData.notes}
                            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                            className="bg-gray-800 border-gray-700 text-gray-100"
                        />
                    </div>

                    <div className="flex justify-end gap-2 pt-2">
                        <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                            Cancelar
                        </Button>
                        <Button
                            type="submit"
                            disabled={loading}
                            className="bg-teal-600 hover:bg-teal-700"
                        >
                            {loading ? 'Guardando...' : 'Guardar Cambios'}
                        </Button>
                    </div>
                </form>
            </DialogContent>
        </Dialog>
    );
}
