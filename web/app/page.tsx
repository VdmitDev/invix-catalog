import Link from 'next/link';

type Product = {
  id: number;
  title: string;
  image_url: string;
  created_at: string;
};

type ProductList = {
  items: Product[];
  limit: number;
  offset: number;
};

export const dynamic = 'force-dynamic';

async function getProducts(): Promise<Product[]> {
  const apiBase = process.env.API_BASE_URL ?? 'http://api:8000';
  const response = await fetch(`${apiBase}/api/products?limit=100&offset=0`, {
    cache: 'no-store',
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`Catalog API returned ${response.status}`);
  const payload = (await response.json()) as ProductList;
  return payload.items;
}

export default async function CatalogPage() {
  let products: Product[] = [];
  let hasError = false;
  try {
    products = await getProducts();
  } catch {
    hasError = true;
  }

  return (
    <main className="page-shell">
      <header className="topbar">
        <Link className="brand" href="/" aria-label="Каталог — главная">
          <span className="brand-mark">К</span>
          <span>Каталог</span>
        </Link>
        <span className="topbar-note">Простой каталог товаров</span>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">НАШИ ТОВАРЫ</p>
          <h1>Каталог</h1>
          <p className="hero-description">Выберите товар, чтобы посмотреть фотографии и подробности.</p>
        </div>
        <div className="hero-count">
          <span className="count-number">{products.length}</span>
          <span className="count-label">товаров на странице</span>
        </div>
      </section>

      {hasError ? (
        <section className="empty-state error-state">
          <div className="empty-icon">!</div>
          <h2>Каталог временно недоступен</h2>
          <p>Не удалось связаться с сервисом каталога. Попробуйте обновить страницу чуть позже.</p>
        </section>
      ) : products.length === 0 ? (
        <section className="empty-state">
          <div className="empty-icon">＋</div>
          <h2>Пока нет товаров</h2>
          <p>Администратор может добавить первый товар через Telegram-бота, отправив фото с названием в подписи.</p>
        </section>
      ) : (
        <section className="product-grid" aria-label="Список товаров">
          {products.map((product) => (
            <Link className="product-card" href={`/products/${product.id}`} key={product.id}>
              <div className="product-image-wrap">
                {/* The URL is served by the configured public MinIO endpoint. */}
                <img className="product-image" src={product.image_url} alt={product.title} loading="lazy" />
              </div>
              <div className="product-content">
                <span className="product-id">ТОВАР №{product.id}</span>
                <h2>{product.title}</h2>
                <span className="product-action">Посмотреть <span aria-hidden="true">→</span></span>
              </div>
            </Link>
          ))}
        </section>
      )}

      <footer className="footer">
        <span>Каталог доступен в браузере и Telegram</span>
        <span>Обновление данных при каждом запросе</span>
      </footer>
    </main>
  );
}
