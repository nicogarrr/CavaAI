'use server';

import { connectToDatabase } from '@/database/mongoose';
import { FamousInvestorModel, type FamousInvestor } from '@/database/models/famous-investor.model';

// Datos iniciales de inversores famosos
const INITIAL_INVESTORS = [
    {
        name: 'Warren Buffett',
        description: 'CEO de Berkshire Hathaway, conocido como el "Oráculo de Omaha"',
        positions: [
            { symbol: 'AAPL', company: 'Apple Inc.', source: '13F' },
            { symbol: 'BAC', company: 'Bank of America Corp', source: '13F' },
            { symbol: 'KO', company: 'The Coca-Cola Company', source: '13F' },
            { symbol: 'AXP', company: 'American Express Co', source: '13F' },
        ],
    },
    {
        name: 'Ray Dalio',
        description: 'Fundador de Bridgewater Associates, el mayor fondo de cobertura del mundo',
        positions: [
            { symbol: 'AAPL', company: 'Apple Inc.', source: 'estimated' },
            { symbol: 'MSFT', company: 'Microsoft Corporation', source: 'estimated' },
            { symbol: 'GOOGL', company: 'Alphabet Inc.', source: 'estimated' },
        ],
    },
    {
        name: 'Bill Gates',
        description: 'Fundador de Microsoft, filántropo y gestor de fondos de inversión',
        positions: [
            { symbol: 'MSFT', company: 'Microsoft Corporation', source: 'public' },
            { symbol: 'BRK.B', company: 'Berkshire Hathaway Inc.', source: 'public' },
            { symbol: 'CNI', company: 'Canadian National Railway', source: 'public' },
        ],
    },
];

export async function getFamousInvestors(): Promise<FamousInvestor[]> {
    try {
        // Durante el build, retornamos datos iniciales sin intentar conectar a MongoDB
        const isBuildTime = process.env.NEXT_PHASE === 'phase-production-build' || 
                           process.env.NEXT_PHASE === 'phase-development-build';
        
        if (isBuildTime) {
            // Durante el build, retornamos los datos iniciales formateados
            return INITIAL_INVESTORS.map((investor, index) => ({
                _id: `build-${index}`,
                name: investor.name,
                description: investor.description,
                positions: investor.positions,
                lastUpdated: new Date(),
                createdAt: new Date(),
                updatedAt: new Date(),
            })) as FamousInvestor[];
        }
        
        const mongoose = await connectToDatabase();
        
        // Si no hay conexión a MongoDB durante runtime, retornamos datos iniciales
        if (!mongoose || !mongoose.connection) {
            return INITIAL_INVESTORS.map((investor, index) => ({
                _id: `fallback-${index}`,
                name: investor.name,
                description: investor.description,
                positions: investor.positions,
                lastUpdated: new Date(),
                createdAt: new Date(),
                updatedAt: new Date(),
            })) as FamousInvestor[];
        }
        
        let investors = await FamousInvestorModel.find().sort({ name: 1 }).lean();

        // Si no hay inversores, crear los iniciales
        if (investors.length === 0) {
            await FamousInvestorModel.insertMany(INITIAL_INVESTORS);
            investors = await FamousInvestorModel.find().sort({ name: 1 }).lean();
        }

        return JSON.parse(JSON.stringify(investors));
    } catch (error) {
        console.error('Error getting famous investors:', error);
        // En caso de error, retornar datos iniciales como fallback
        return INITIAL_INVESTORS.map((investor, index) => ({
            _id: `error-${index}`,
            name: investor.name,
            description: investor.description,
            positions: investor.positions,
            lastUpdated: new Date(),
            createdAt: new Date(),
            updatedAt: new Date(),
        })) as FamousInvestor[];
    }
}

export async function getFamousInvestorById(investorId: string): Promise<FamousInvestor | null> {
    try {
        // Durante el build, retornamos null o buscamos en datos iniciales
        const isBuildTime = process.env.NEXT_PHASE === 'phase-production-build' || 
                           process.env.NEXT_PHASE === 'phase-development-build';
        
        if (isBuildTime) {
            // Buscar en datos iniciales por ID
            const index = parseInt(investorId.replace(/^(build-|fallback-|error-)/, ''));
            if (!isNaN(index) && INITIAL_INVESTORS[index]) {
                const investor = INITIAL_INVESTORS[index];
                return {
                    _id: investorId,
                    name: investor.name,
                    description: investor.description,
                    positions: investor.positions,
                    lastUpdated: new Date(),
                    createdAt: new Date(),
                    updatedAt: new Date(),
                } as FamousInvestor;
            }
            return null;
        }
        
        const mongoose = await connectToDatabase();
        
        // Si no hay conexión a MongoDB durante runtime, buscar en datos iniciales
        if (!mongoose || !mongoose.connection) {
            const index = parseInt(investorId.replace(/^(fallback-|error-)/, ''));
            if (!isNaN(index) && INITIAL_INVESTORS[index]) {
                const investor = INITIAL_INVESTORS[index];
                return {
                    _id: investorId,
                    name: investor.name,
                    description: investor.description,
                    positions: investor.positions,
                    lastUpdated: new Date(),
                    createdAt: new Date(),
                    updatedAt: new Date(),
                } as FamousInvestor;
            }
            return null;
        }
        
        const investor = await FamousInvestorModel.findById(investorId).lean();
        
        return investor ? JSON.parse(JSON.stringify(investor)) : null;
    } catch (error) {
        console.error('Error getting famous investor:', error);
        // En caso de error, retornar null en lugar de lanzar error
        return null;
    }
}

