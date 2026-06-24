import { motion } from 'framer-motion';
import { NewsCard } from '../components/NewsCard';
import { Link } from 'react-router-dom';
import { newsEntries } from '../data/news';

/**
 * News — полная лента обновлений проекта.
 * Компактный hero + список + CTA на главную.
 */
export function News() {
  return (
    <>
      <header className="hero hero-compact" role="banner">
        <div className="hero-inner">
          <motion.h1
            className="hero-title"
            data-text="Лента обновлений"
            initial={{ x: 0, y: 0, opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.8 } }}
          >
            Лента<br /><span className="neon">обновлений</span>
          </motion.h1>
          <p className="hero-sub">
            Релизы, обновления GPU/CUDA, поддержка новых моделей и фиксы.
            Хронология сверху вниз — самое свежее наверху.
          </p>
        </div>
        <div className="hero-glow-line" aria-hidden="true" />
      </header>

      <section className="section" aria-labelledby="news-title">
        <div className="section-header">
          <span className="section-eyebrow">Changelog</span>
          <h2 id="news-title">История изменений</h2>
          <p className="section-subtitle">
            Каждый релиз снабжён тегом и подробностями — что именно поменялось в скриптах
            и какие новые возможности появились.
          </p>
        </div>

        <div className="news-list">
          {newsEntries.map((e, i) => <NewsCard key={i} entry={e} />)}
        </div>

        <p className="news-cta">
          <Link to="/" className="btn btn-secondary">← Вернуться на главную</Link>
        </p>
      </section>
    </>
  );
}
