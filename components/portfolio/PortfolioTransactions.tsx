'use client';

import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Trash2 } from 'lucide-react';
import { deleteTransaction } from '@/lib/actions/portfolio.actions';
import { useRouter } from 'next/navigation';
import EditTransactionDialog from './EditTransactionDialog';

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
  transactions: Transaction[];
  userId: string;
};

export default function PortfolioTransactions({ transactions, userId }: Props) {
  const router = useRouter();
  const [deleting, setDeleting] = useState<string | null>(null);

  const handleDelete = async (transactionId: string) => {
    if (!confirm('¿Estás seguro de eliminar esta transacción?')) return;

    setDeleting(transactionId);
    const result = await deleteTransaction(userId, transactionId);

    if (result.success) {
      router.refresh();
    } else {
      alert('Error al eliminar la transacción');
    }
    setDeleting(null);
  };

  return (
    <Card className="bg-gray-800/50 border-gray-700">
      <CardHeader>
        <CardTitle className="text-gray-100">Historial de Transacciones</CardTitle>
      </CardHeader>
      <CardContent>
        {transactions.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-400">No hay transacciones registradas</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fecha</TableHead>
                  <TableHead>Símbolo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">Cantidad</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-center">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transactions.map((tx) => (
                  <TableRow key={tx._id}>
                    <TableCell className="text-gray-300">
                      {new Date(tx.date).toLocaleDateString('es-ES')}
                    </TableCell>
                    <TableCell className="font-mono font-bold text-gray-100">
                      {tx.symbol}
                    </TableCell>
                    <TableCell>
                      <Badge variant={tx.type === 'buy' ? 'default' : 'secondary'}>
                        {tx.type === 'buy' ? 'Compra' : 'Venta'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-gray-300">
                      {tx.quantity}
                    </TableCell>
                    <TableCell className="text-right text-gray-300">
                      ${tx.price.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right font-semibold text-gray-100">
                      ${(tx.quantity * tx.price).toFixed(2)}
                    </TableCell>
                    <TableCell className="text-center">
                      <div className="flex justify-center gap-1">
                        <EditTransactionDialog transaction={tx} userId={userId} />
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(tx._id)}
                          disabled={deleting === tx._id}
                          className="text-red-400 hover:text-red-300 hover:bg-red-950/20"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
