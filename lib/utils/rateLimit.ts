/**
 * Rate limiting simple en memoria
 * Para producción, usar @upstash/ratelimit con Redis
 */

interface RateLimitStore {
  [key: string]: {
    count: number;
    resetAt: number;
  };
}

const store: RateLimitStore = {};

/**
 * Rate limiter simple en memoria
 * @param identifier Identificador único (IP, userId, etc.)
 * @param windowMs Ventana de tiempo en milisegundos
 * @param maxRequests Máximo de requests en la ventana
 * @returns true si se permite el request, false si se excede el límite
 */
export function rateLimit(
  identifier: string,
  windowMs: number,
  maxRequests: number
): { allowed: boolean; remaining: number; resetAt: number } {
  const now = Date.now();
  const key = identifier;
  
  if (!store[key] || store[key].resetAt < now) {
    // Nueva ventana
    store[key] = {
      count: 1,
      resetAt: now + windowMs,
    };
    
    return {
      allowed: true,
      remaining: maxRequests - 1,
      resetAt: store[key].resetAt,
    };
  }
  
  store[key].count += 1;
  
  if (store[key].count > maxRequests) {
    return {
      allowed: false,
      remaining: 0,
      resetAt: store[key].resetAt,
    };
  }
  
  return {
    allowed: true,
    remaining: maxRequests - store[key].count,
    resetAt: store[key].resetAt,
  };
}

/**
 * Limpiar entradas expiradas periódicamente
 */
setInterval(() => {
  const now = Date.now();
  Object.keys(store).forEach((key) => {
    if (store[key].resetAt < now) {
      delete store[key];
    }
  });
}, 60000); // Limpiar cada minuto

