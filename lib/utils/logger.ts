type LogLevel = 'error' | 'warn' | 'info' | 'debug';

const levelPriority: Record<LogLevel, number> = {
  error: 0,
  warn: 1,
  info: 2,
  debug: 3,
};

const currentLevel: LogLevel = (process.env.NODE_ENV === 'production' ? 'info' : 'debug');

function shouldLog(level: LogLevel): boolean {
  return levelPriority[level] <= levelPriority[currentLevel];
}

export const logger = {
  error: (...args: unknown[]) => {
    if (shouldLog('error')) console.error('[ERROR]', ...args);
  },
  warn: (...args: unknown[]) => {
    if (shouldLog('warn')) console.warn('[WARN]', ...args);
  },
  info: (...args: unknown[]) => {
    if (shouldLog('info')) console.info('[INFO]', ...args);
  },
  debug: (...args: unknown[]) => {
    if (shouldLog('debug')) console.debug('[DEBUG]', ...args);
  },
};

export default logger;


