import Link from 'next/link';
import { notFound } from 'next/navigation';

type Product = { id: number; title: string; image_url: string; created_at: string };

export const dynamic = 'force-dynamic';

async function getProduct(id: string): Promise<Product | null> {
  if (!/^\d+$/.test(id)) return null;
  const response = await fetch(`${process.env.API_BASE_URL ?? 'http://api:8000'}/api/products/${id}`, {
    cache: 'no-store',
    signal: AbortSignal.timeout(5000),
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Catalog API returned ${response.status}`);
  return (await response.json()) as Product;
}

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const product = await getProduct(id);
  if (!product) notFound();

  return (
    <main className="page-shell">
      <header className="topbar">
        <Link className="brand" href="/"><span className="brand-mark">К</span><span>Каталог</span></Link>
        <Link className="back-link" href="/">← Все товары</Link>
      </header>
      <section className="detail-layout">
        <div className="detail-image-wrap"><img className="detail-image" src={product.image_url} alt={product.title} /></div>
        <div className="detail-copy">
          <span className="eyebrow">ТОВАР №{product.id}</span>
          <h1>{product.title}</h1>
          <p>Фотография и название этого товара загружены в каталог через Telegram-бота.</p>
          <Link href="/" className="primary-link">Вернуться в каталог</Link>
        </div>
      </section>
      <footer className="footer"><span>Каталог товаров</span><span>Данные предоставляются сервисом FastAPI</span></footer>
    </main>
  );
}
