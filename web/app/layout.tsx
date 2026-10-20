import type { Metadata, Viewport } from 'next';
import Script from 'next/script';
import type { ReactNode } from 'react';
import { TelegramMiniAppInit } from '@/components/telegram-mini-app';
import './globals.css';

export const metadata: Metadata = {
  title: 'Каталог товаров',
  description: 'Каталог товаров — доступен в браузере и Telegram Mini App.',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#f6f7f9',
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <Script src="https://telegram.org/js/telegram-web-app.js" strategy="beforeInteractive" />
        <TelegramMiniAppInit />
        {children}
      </body>
    </html>
  );
}
