'use server';

import { jsonBody, researchRequest } from '@/lib/research/client';
import { ValidationError } from '@/lib/types/errors';

export type AlertType = 'price_above' | 'price_below' | 'price_change' | 'news' | 'earnings';

export interface Alert {
    _id: string;
    symbol: string;
    type: AlertType;
    condition: {
        operator: '>' | '<' | '>=' | '<=' | '==';
        value: number | string;
    };
    isActive: boolean;
    lastTriggered?: string;
    createdAt: string;
    updatedAt: string;
    /** Estado de evaluacion del motor (job alert_rule_evaluation, cada 5 min). */
    channels: string[];
    triggerCount: number;
    lastEvaluatedAt?: string;
    lastValue?: string | null;
    lastResultStatus?: string;
}

export interface CreateAlertInput {
    symbol: string;
    type: AlertType;
    condition: Alert['condition'];
}

type ResearchAlertRule = {
    id: number;
    active: boolean;
    rule_type: Alert['type'];
    condition: Alert['condition'];
    channels: string[];
    trigger_count: number;
    last_evaluated_at?: string | null;
    last_value?: string | null;
    last_result?: { status?: string } | null;
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
        channels: alert.channels ?? ['in_app'],
        triggerCount: alert.trigger_count ?? 0,
        lastEvaluatedAt: alert.last_evaluated_at ?? undefined,
        lastValue: alert.last_value ?? null,
        lastResultStatus: alert.last_result?.status,
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

export interface TelegramStatus {
    enabled: boolean;
    has_bot_token: boolean;
    has_chat_id: boolean;
    configured: boolean;
}

/** GET /api/alerts/telegram-status — presencia de config Telegram (sin secretos). */
export async function getTelegramStatus(): Promise<TelegramStatus> {
    return researchRequest<TelegramStatus>('/api/alerts/telegram-status');
}

export interface TriggeredAlertDelivery {
    id: number;
    title: string;
    message: string;
    severity: string;
    status: string;
    alert_type: string;
    channels: string[];
    deliveries: Record<string, { status: string; attempted_at?: string; error?: string | null }>;
    createdAt: string;
}

type ResearchAlertRow = {
    id: number;
    title: string;
    message: string;
    severity: string;
    status: string;
    alert_type: string;
    channels: string[];
    metadata: { deliveries?: TriggeredAlertDelivery['deliveries'] };
    created_at: string;
};

/** GET /api/alerts — ultimas alertas disparadas con su estado de entrega por canal. */
export async function getRecentTriggeredAlerts(limit = 20): Promise<TriggeredAlertDelivery[]> {
    const rows = await researchRequest<ResearchAlertRow[]>(`/api/alerts?limit=${limit}`);
    return (rows ?? []).map((row) => ({
        id: row.id,
        title: row.title,
        message: row.message,
        severity: row.severity,
        status: row.status,
        alert_type: row.alert_type,
        channels: row.channels ?? [],
        deliveries: row.metadata?.deliveries ?? {},
        createdAt: row.created_at,
    }));
}
