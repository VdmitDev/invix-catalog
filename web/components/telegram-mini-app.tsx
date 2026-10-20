'use client';

import { useEffect } from 'react';

type TelegramWebApp = {
  ready: () => void;
  expand: () => void;
};

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export function TelegramMiniAppInit() {
  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    if (!webApp) return;
    webApp.ready();
    webApp.expand();
  }, []);

  return null;
}
