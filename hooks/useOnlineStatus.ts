"use client";

import { useSyncExternalStore } from 'react';

export function useOnlineStatus(): boolean {
  return useSyncExternalStore((onStoreChange) => {
    window.addEventListener('online', onStoreChange);
    window.addEventListener('offline', onStoreChange);
    return () => {
      window.removeEventListener('online', onStoreChange);
      window.removeEventListener('offline', onStoreChange);
    };
  }, () => navigator.onLine, () => true);
}


