'use client';

import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Trash2 } from 'lucide-react';
import { deletePortfolio } from '@/lib/actions/portfolio.actions';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';

type PortfolioListProps = {
    portfolios: Portfolio[];
};

export default function PortfolioList({ portfolios }: PortfolioListProps) {
    const router = useRouter();

    const handleDelete = async (portfolioId: string, portfolioName: string) => {
        if (!confirm(`¿Estás seguro de eliminar la cartera "${portfolioName}"?`)) {
            return;
        }

        try {
            await deletePortfolio(portfolioId);
            toast.success('Cartera eliminada correctamente');
            router.refresh();
        } catch (error) {
            console.error('Error al eliminar cartera:', error);
            toast.error('Error al eliminar la cartera');
        }
    };

    if (portfolios.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-16 text-center">
                <h3 className="text-xl font-semibold mb-2">No tienes carteras todavía</h3>
                <p className="text-muted-foreground mb-6">
                    Crea tu primera cartera para empezar a gestionar tus inversiones
                </p>
            </div>
        );
    }

    return (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {portfolios.map((portfolio) => (
                <div
                    key={portfolio._id}
                    className="border rounded-lg p-6 hover:shadow-lg transition-shadow"
                >
                    <div className="flex items-start justify-between mb-4">
                        <div className="flex-1">
                            <h3 className="text-xl font-semibold mb-2">{portfolio.name}</h3>
                            {portfolio.description && (
                                <p className="text-sm text-muted-foreground line-clamp-2">
                                    {portfolio.description}
                                </p>
                            )}
                        </div>
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleDelete(portfolio._id, portfolio.name)}
                            className="ml-2"
                        >
                            <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                    </div>

                    <div className="space-y-2 mb-4">
                        <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Posiciones:</span>
                            <span className="font-medium">{portfolio.positions.length}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Creada:</span>
                            <span className="font-medium">
                                {new Date(portfolio.createdAt).toLocaleDateString('es-ES')}
                            </span>
                        </div>
                    </div>

                    <Link href={`/portfolio/${portfolio._id}`}>
                        <Button className="w-full">Ver Detalles</Button>
                    </Link>
                </div>
            ))}
        </div>
    );
}

