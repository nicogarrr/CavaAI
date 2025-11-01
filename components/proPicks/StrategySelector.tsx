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
}

export default function StrategySelector({ strategies, currentStrategy }: StrategySelectorProps) {
    const router = useRouter();

    const handleStrategyChange = (strategyId: string) => {
        router.push(`/propicks?strategy=${strategyId}`);
        router.refresh();
    };

    return (
        <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-gray-400">Estrategia:</label>
            <Select value={currentStrategy} onValueChange={handleStrategyChange}>
                <SelectTrigger className="w-[300px] bg-gray-800 border-gray-700 text-gray-300">
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

