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

type ResearchAlertRule = {
    id: number;
    active: boolean;
    rule_type: Alert['type'];
    condition: Alert['condition'];
    last_triggered_at?: string | null;
    created_at: string;
    updated_at: string;
    metadata: {
        ticker?: string;
    };
};

function toAlert(alert: ResearchAlertRule): Alert {
    return {
        _id: String(alert.id),
        symbol: alert.metadata.ticker ?? '',
        type: alert.rule_type,
        condition: alert.condition,
        isActive: alert.active,
        lastTriggered: alert.last_triggered_at ?? undefined,
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
    const alert = await researchRequest<ResearchAlertRule>('/api/alerts', {
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
    const alerts = await researchRequest<ResearchAlertRule[]>('/api/alerts/rules?active=true');
    return alerts.map(toAlert);
}

export async function deleteAlert(alertId: string): Promise<void> {
    if (!/^\d+$/.test(alertId)) throw new ValidationError('Invalid alert id', 'alertId');
    await researchRequest(`/api/alerts/rules/${alertId}`, {
        method: 'DELETE',
    });
}
