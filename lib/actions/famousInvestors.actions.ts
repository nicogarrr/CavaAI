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
        await connectToDatabase();
        
        let investors = await FamousInvestorModel.find().sort({ name: 1 }).lean();

        // Si no hay inversores, crear los iniciales
        if (investors.length === 0) {
            await FamousInvestorModel.insertMany(INITIAL_INVESTORS);
            investors = await FamousInvestorModel.find().sort({ name: 1 }).lean();
        }

        return JSON.parse(JSON.stringify(investors));
    } catch (error) {
        console.error('Error getting famous investors:', error);
        throw error;
    }
}

export async function getFamousInvestorById(investorId: string): Promise<FamousInvestor | null> {
    try {
        await connectToDatabase();
        const investor = await FamousInvestorModel.findById(investorId).lean();
        
        return investor ? JSON.parse(JSON.stringify(investor)) : null;
    } catch (error) {
        console.error('Error getting famous investor:', error);
        throw error;
    }
}

