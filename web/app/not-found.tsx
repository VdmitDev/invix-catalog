import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="page-shell">
      <header className="topbar"><Link className="brand" href="/"><span className="brand-mark">К</span><span>Каталог</span></Link></header>
      <section className="empty-state"><div className="empty-icon">?</div><h1>Товар не найден</h1><p>Возможно, он был удалён или ссылка неверная.</p><Link className="primary-link" href="/">Вернуться в каталог</Link></section>
    </main>
  );
}
