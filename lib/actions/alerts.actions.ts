'use server';

import { jsonBody, researchRequest } from '@/lib/research/client';
import { ValidationError } from '@/lib/types/errors';

export interface Alert {
    _id: string;
    symbol: string;
    type: 'price_above' | 'price_below' | 'price_change' | 'news' | 'earnings';
    condition: {
        operator: '>' | '<' | '>=' | '<=' | '==';
        value: number | string;
    };
    isActive: boolean;
    lastTriggered?: string;
    createdAt: string;
    updatedAt: string;
}

export interface CreateAlertInput {
    symbol: string;
    type: Alert['type'];
    condition: Alert['condition'];
}

type ResearchAlert = {
    id: number;
    status: string;
    alert_type: Alert['type'];
    created_at: string;
    updated_at: string;
    metadata: {
        ticker?: string;
        condition?: Alert['condition'];
    };
};

function toAlert(alert: ResearchAlert): Alert {
    return {
        _id: String(alert.id),
        symbol: alert.metadata.ticker ?? '',
        type: alert.alert_type,
        condition: alert.metadata.condition ?? { operator: '==', value: '' },
        isActive: !['resolved', 'dismissed'].includes(alert.status),
        createdAt: alert.created_at,
        updatedAt: alert.updated_at,
    };
}

export async function createAlert(input: CreateAlertInput): Promise<Alert> {
    const symbol = input.symbol.trim().toUpperCase();
    if (!/^[A-Z0-9.\-]{1,20}$/.test(symbol)) {
        throw new ValidationError('A valid ticker is required', 'symbol');
    }
    await researchRequest('/api/companies/ensure', {
        method: 'POST',
        body: jsonBody({ ticker: symbol }),
    });
    const alert = await researchRequest<ResearchAlert>('/api/alerts', {
        method: 'POST',
        body: jsonBody({
            ticker: symbol,
            alert_type: input.type,
            operator: input.condition.operator,
            value: input.condition.value,
        }),
    });
    return toAlert(alert);
}

export async function getUserAlerts(): Promise<Alert[]> {
    const alerts = await researchRequest<ResearchAlert[]>('/api/alerts?include_snoozed=true');
    return alerts.filter((alert) => !['resolved', 'dismissed'].includes(alert.status)).map(toAlert);
}

export async function deleteAlert(alertId: string): Promise<void> {
    if (!/^\d+$/.test(alertId)) throw new ValidationError('Invalid alert id', 'alertId');
    await researchRequest(`/api/alerts/${alertId}/action`, {
        method: 'POST',
        body: jsonBody({ action: 'resolve', actor: 'user' }),
    });
}
