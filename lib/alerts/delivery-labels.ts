/**
 * Etiquetas ES de canal y estado de entrega de una alerta. El valor interno
 * (in_app, delivered...) no se enseña tal cual; uno desconocido se muestra
 * crudo (visible y honesto, nunca inventado). «sin registro» = el motor no
 * guardó entrega para ese canal: no se disfraza de pendiente ni de entregada.
 */
const CANALES: Record<string, string> = {
    in_app: 'en la app',
    email: 'correo',
    telegram: 'Telegram',
    push: 'notificación',
};

const ESTADOS_ENTREGA: Record<string, string> = {
    delivered: 'entregada',
    failed: 'fallida',
    pending: 'pendiente',
    skipped: 'omitida',
    'sin registro': 'sin registro de entrega',
};

export function etiquetaCanal(value: string): string {
    return CANALES[value] ?? value;
}

export function etiquetaEstadoEntrega(value: string): string {
    return ESTADOS_ENTREGA[value] ?? value;
}
