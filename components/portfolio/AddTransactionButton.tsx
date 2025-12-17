'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
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
import { Plus, Search, TrendingUp, Loader2 } from 'lucide-react';
import { addTransaction } from '@/lib/actions/portfolio.actions';
import { searchStocks } from '@/lib/actions/finnhub.actions';
import { useRouter } from 'next/navigation';

type Props = {
  userId: string;
};

interface StockResult {
  symbol: string;
  name: string;
  exchange: string;
  type: string;
}

export default function AddTransactionButton({ userId }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<StockResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const [formData, setFormData] = useState({
    symbol: '',
    companyName: '',
    type: 'buy' as 'buy' | 'sell',
    quantity: '',
    price: '',
    date: new Date().toISOString().split('T')[0],
    notes: '',
  });

  // Búsqueda inteligente con debounce
  const handleSearch = useCallback(async (query: string) => {
    if (query.length < 1) {
      setSearchResults([]);
      setShowResults(false);
      return;
    }

    setSearchLoading(true);
    try {
      const results = await searchStocks(query);
      setSearchResults(results?.slice(0, 8) || []);
      setShowResults(true);
    } catch (error) {
      console.error('Error searching stocks:', error);
      setSearchResults([]);
    }
    setSearchLoading(false);
  }, []);

  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    if (searchQuery.length >= 1) {
      searchTimeoutRef.current = setTimeout(() => {
        handleSearch(searchQuery);
      }, 300);
    } else {
      setSearchResults([]);
      setShowResults(false);
    }

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchQuery, handleSearch]);

  const selectStock = (stock: StockResult) => {
    setFormData({
      ...formData,
      symbol: stock.symbol,
      companyName: stock.name
    });
    setSearchQuery(stock.symbol);
    setShowResults(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const result = await addTransaction(
      userId,
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
      setFormData({
        symbol: '',
        companyName: '',
        type: 'buy',
        quantity: '',
        price: '',
        date: new Date().toISOString().split('T')[0],
        notes: '',
      });
      setSearchQuery('');
      router.refresh();
    } else {
      alert('Error al agregar la transacción');
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="flex items-center gap-2 bg-teal-600 hover:bg-teal-700">
          <Plus className="h-4 w-4" />
          Agregar Inversión
        </Button>
      </DialogTrigger>
      <DialogContent className="bg-gray-900 border-gray-700 max-w-md">
        <DialogHeader>
          <DialogTitle className="text-gray-100">Nueva Inversión</DialogTitle>
          <DialogDescription className="text-gray-400">
            Registra una compra o venta de acciones
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Buscador Inteligente */}
          <div className="space-y-2 relative">
            <Label htmlFor="symbol" className="text-gray-300">Buscar Acción</Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500" />
              <Input
                id="symbol"
                placeholder="Buscar por nombre o símbolo (ej: Apple, AAPL)"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  if (e.target.value !== formData.symbol) {
                    setFormData({ ...formData, symbol: '', companyName: '' });
                  }
                }}
                className="bg-gray-800 border-gray-700 text-gray-100 pl-10"
              />
              {searchLoading && (
                <Loader2 className="absolute right-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500 animate-spin" />
              )}
            </div>

            {/* Dropdown de resultados */}
            {showResults && searchResults.length > 0 && (
              <div className="absolute z-50 w-full mt-1 bg-gray-800 border border-gray-700 rounded-md shadow-lg max-h-60 overflow-auto">
                {searchResults.map((stock, index) => (
                  <button
                    key={`${stock.symbol}-${index}`}
                    type="button"
                    onClick={() => selectStock(stock)}
                    className="w-full px-4 py-3 text-left hover:bg-gray-700 flex items-center gap-3 border-b border-gray-700 last:border-0"
                  >
                    <TrendingUp className="h-4 w-4 text-teal-400" />
                    <div>
                      <div className="text-white font-medium">{stock.symbol}</div>
                      <div className="text-sm text-gray-400">{stock.name}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {/* Acción seleccionada */}
            {formData.symbol && (
              <div className="flex items-center gap-2 p-2 bg-teal-900/30 rounded border border-teal-700">
                <TrendingUp className="h-4 w-4 text-teal-400" />
                <span className="text-teal-300 font-medium">{formData.symbol}</span>
                <span className="text-gray-400 text-sm">- {formData.companyName}</span>
              </div>
            )}
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
                placeholder="10"
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
                placeholder="150.00"
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
              placeholder="Notas sobre la transacción"
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
              disabled={loading || !formData.symbol}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {loading ? 'Guardando...' : 'Guardar Inversión'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
