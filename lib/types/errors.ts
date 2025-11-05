/**
 * Tipos centralizados para manejo de errores
 * Reemplaza el uso de 'any' en catch blocks
 */

/**
 * Error base de la aplicación
 */
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly statusCode: number = 500,
    public readonly cause?: unknown
  ) {
    super(message);
    this.name = 'AppError';
  }
}

/**
 * Error de validación
 */
export class ValidationError extends AppError {
  constructor(message: string, public readonly field?: string) {
    super(message, 'VALIDATION_ERROR', 400);
    this.name = 'ValidationError';
  }
}

/**
 * Error de autenticación
 */
export class AuthenticationError extends AppError {
  constructor(message: string = 'Authentication failed') {
    super(message, 'AUTH_ERROR', 401);
    this.name = 'AuthenticationError';
  }
}

/**
 * Error de autorización
 */
export class AuthorizationError extends AppError {
  constructor(message: string = 'Access denied') {
    super(message, 'AUTHORIZATION_ERROR', 403);
    this.name = 'AuthorizationError';
  }
}

/**
 * Error de recurso no encontrado
 */
export class NotFoundError extends AppError {
  constructor(resource: string = 'Resource') {
    super(`${resource} not found`, 'NOT_FOUND', 404);
    this.name = 'NotFoundError';
  }
}

/**
 * Error de rate limit
 */
export class RateLimitError extends AppError {
  constructor(message: string = 'Rate limit exceeded') {
    super(message, 'RATE_LIMIT_ERROR', 429);
    this.name = 'RateLimitError';
  }
}

/**
 * Error de API externa
 */
export class ExternalAPIError extends AppError {
  constructor(
    message: string,
    public readonly service: string,
    public readonly originalError?: unknown
  ) {
    super(message, 'EXTERNAL_API_ERROR', 502, originalError);
    this.name = 'ExternalAPIError';
  }
}

/**
 * Error de base de datos
 */
export class DatabaseError extends AppError {
  constructor(message: string, cause?: unknown) {
    super(message, 'DATABASE_ERROR', 500, cause);
    this.name = 'DatabaseError';
  }
}

/**
 * Type guard para verificar si un error es de tipo AppError
 */
export function isAppError(error: unknown): error is AppError {
  return error instanceof AppError;
}

/**
 * Type guard para verificar si un error es un Error estándar
 */
export function isError(error: unknown): error is Error {
  return error instanceof Error;
}

/**
 * Convierte un error desconocido a un AppError
 */
export function toAppError(error: unknown, defaultMessage: string = 'An unexpected error occurred'): AppError {
  if (isAppError(error)) {
    return error;
  }
  
  if (isError(error)) {
    return new AppError(error.message, 'UNKNOWN_ERROR', 500, error);
  }
  
  return new AppError(defaultMessage, 'UNKNOWN_ERROR', 500, error);
}

/**
 * Extrae mensaje de error de forma segura
 */
export function getErrorMessage(error: unknown): string {
  if (isAppError(error) || isError(error)) {
    return error.message;
  }
  
  if (typeof error === 'string') {
    return error;
  }
  
  return 'An unknown error occurred';
}

