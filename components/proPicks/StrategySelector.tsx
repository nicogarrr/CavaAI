'use client';

import { useRouter } from 'next/navigation';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';

interface Strategy {
    id: string;
    name: string;
    description: string;
}

interface StrategySelectorProps {
    strategies: Strategy[];
    currentStrategy: string;
    /** Callback opcional para notificar cambios sin depender de la navegación */
    onStrategyChange?: (strategyId: string) => void;
}

export default function StrategySelector({ strategies, currentStrategy, onStrategyChange }: StrategySelectorProps) {
    const router = useRouter();

    const handleStrategyChange = (strategyId: string) => {
        onStrategyChange?.(strategyId);
        router.push(`/propicks?strategy=${strategyId}`);
        router.refresh();
    };

    return (
        <div className="flex w-full min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            <label className="shrink-0 text-sm font-medium text-gray-400">Estrategia:</label>
            <Select value={currentStrategy} onValueChange={handleStrategyChange}>
                <SelectTrigger className="h-11 w-full border-gray-700 bg-gray-800 text-sm text-gray-300 sm:w-[300px]">
                    <SelectValue placeholder="Seleccionar estrategia" />
                </SelectTrigger>
                <SelectContent className="bg-gray-800 border-gray-700">
                    {strategies.map((strategy) => (
                        <SelectItem 
                            key={strategy.id} 
                            value={strategy.id}
                            className="text-gray-300 hover:bg-gray-700"
                        >
                            <div className="flex flex-col">
                                <span className="font-medium">{strategy.name}</span>
                                <span className="text-xs text-gray-500">{strategy.description}</span>
                            </div>
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );
}

