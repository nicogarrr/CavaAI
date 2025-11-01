'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus } from 'lucide-react';
import { createPortfolio } from '@/lib/actions/portfolio.actions';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';

export default function CreatePortfolioButton() {
    const [open, setOpen] = useState(false);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const router = useRouter();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!name.trim()) {
            toast.error('El nombre es requerido');
            return;
        }

        setIsLoading(true);

        try {
            const newPortfolio = await createPortfolio(name.trim(), description.trim() || undefined);
            toast.success('Cartera creada correctamente');
            setName('');
            setDescription('');
            setOpen(false);
            // Redirigir automáticamente a la nueva cartera
            router.push(`/portfolio/${newPortfolio._id}`);
        } catch (error) {
            console.error('Error al crear cartera:', error);
            toast.error('Error al crear la cartera');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button>
                    <Plus className="mr-2 h-4 w-4" />
                    Nueva Cartera
                </Button>
            </DialogTrigger>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Crear Nueva Cartera</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <Label htmlFor="name">Nombre *</Label>
                        <Input
                            id="name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Mi Cartera"
                            required
                        />
                    </div>
                    <div>
                        <Label htmlFor="description">Descripción</Label>
                        <Input
                            id="description"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Descripción opcional"
                        />
                    </div>
                    <div className="flex justify-end gap-2">
                        <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                            Cancelar
                        </Button>
                        <Button type="submit" disabled={isLoading}>
                            {isLoading ? 'Creando...' : 'Crear'}
                        </Button>
                    </div>
                </form>
            </DialogContent>
        </Dialog>
    );
}

