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
    <Card className="bg-[#111111] border-gray-800 h-full flex flex-col">
      <CardHeader className="pb-3 pt-5 border-b border-gray-800/50">
        <CardTitle className="text-gray-100 text-base font-medium flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-blue-500"></span>
          Actividad Reciente
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0 flex-1 overflow-hidden">
        {transactions.length === 0 ? (
          <div className="text-center py-12 px-4">
            <div className="h-10 w-10 bg-gray-800/50 rounded-full flex items-center justify-center mx-auto mb-3">
              <span className="text-gray-500">?</span>
            </div>
            <p className="text-gray-500 text-sm">Sin actividad reciente</p>
          </div>
        ) : (
          <div className="overflow-y-auto h-full max-h-[400px] scrollbar-thin scrollbar-thumb-gray-800 scrollbar-track-transparent">
            <div className="divide-y divide-gray-800/50">
              {transactions.map((tx) => (
                <div key={tx._id} className="p-4 hover:bg-gray-800/30 transition-colors group">
                  <div className="flex items-start justify-between mb-1">
                    <div className="flex items-center gap-3">
                      <div className={`h-8 w-8 rounded-full flex items-center justify-center ${tx.type === 'buy' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-500'
                        }`}>
                        {tx.type === 'buy' ? '+' : '-'}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-gray-200">{tx.symbol}</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded ${tx.type === 'buy' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
                            }`}>
                            {tx.type === 'buy' ? 'Compra' : 'Venta'}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {new Date(tx.date).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' })}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-medium text-gray-200">
                        ${(tx.quantity * tx.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </p>
                      <p className="text-xs text-gray-500">
                        {tx.quantity} acc @ ${tx.price.toFixed(2)}
                      </p>
                    </div>
                  </div>

                  {/* Acciones flotantes (solo visibles en hover) */}
                  <div className="flex justify-end gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <EditTransactionDialog transaction={tx} userId={userId} />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(tx._id)}
                      disabled={deleting === tx._id}
                      className="h-7 w-7 p-0 text-gray-500 hover:text-red-400 hover:bg-red-950/20"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
