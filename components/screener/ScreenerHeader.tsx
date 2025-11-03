'use client';

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Filter, Download, Save, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function ScreenerHeader() {
  const router = useRouter();
  const [savedCriteria, setSavedCriteria] = useState(false);

  const handleSaveCriteria = () => {
    // Save current URL params to localStorage for quick access
    const currentUrl = window.location.search;
    const savedScreeners = JSON.parse(localStorage.getItem('savedScreeners') || '[]');
    const name = `Screener ${new Date().toLocaleDateString()}`;
    savedScreeners.push({ name, params: currentUrl, date: new Date().toISOString() });
    localStorage.setItem('savedScreeners', JSON.stringify(savedScreeners));
    
    setSavedCriteria(true);
    setTimeout(() => setSavedCriteria(false), 2000);
  };

  const handleExportResults = () => {
    // Get current results from the page and export as CSV
    const currentUrl = window.location.href;
    window.dispatchEvent(new CustomEvent('exportScreenerResults'));
  };

  const handleResetFilters = () => {
    router.push('/screener');
  };

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <Filter className="h-6 w-6" />
              <h1 className="text-3xl font-bold">Screener Avanzado</h1>
              <Badge variant="secondary">Beta</Badge>
            </div>
            <p className="text-muted-foreground">
              Encuentra acciones y ETFs que cumplan tus criterios de inversión
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleResetFilters}
              className="flex items-center gap-2"
            >
              <RotateCcw className="h-4 w-4" />
              Reset
            </Button>
            
            <Button
              variant="outline"
              size="sm"
              onClick={handleSaveCriteria}
              className="flex items-center gap-2"
            >
              <Save className="h-4 w-4" />
              {savedCriteria ? 'Guardado!' : 'Guardar'}
            </Button>
            
            <Button
              size="sm"
              onClick={handleExportResults}
              className="flex items-center gap-2"
            >
              <Download className="h-4 w-4" />
              Exportar
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
