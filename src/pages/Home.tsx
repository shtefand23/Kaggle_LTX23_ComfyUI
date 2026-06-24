import { Hero } from '../components/Hero';
import { Bento } from '../components/Bento';
import { Quickstart } from '../components/Quickstart';
import { LiveStats } from '../components/LiveStats';
import { WorkflowsShowcase } from '../components/WorkflowsShowcase';
import { InstallStepper } from '../components/InstallStepper';
import { NewsCard } from '../components/NewsCard';
import { newsTeaser } from '../data/news';
import { Link } from 'react-router-dom';

/**
 * Home — главная страница лендинга.
 * Композиция всех секций в нужном порядке.
 */
export function Home() {
  return (
    <>
      <Hero />
      <Bento />
      <Quickstart />
      <WorkflowsShowcase />
      <InstallStepper />
      <LiveStats />

      <section className="section" id="updates" aria-labelledby="updates-title">
        <div className="section-header">
          <span className="section-eyebrow">Новостная лента</span>
          <h2 id="updates-title">Что нового</h2>
          <p className="section-subtitle">
            Последние релизы и обновления проекта. Полная лента — на странице новостей.
          </p>
        </div>

        <div className="news-teaser-grid">
          {newsTeaser.map((e, i) => <NewsCard key={i} entry={e} />)}
        </div>

        <div className="news-cta">
          <Link to="/news" className="btn btn-primary">Все новости →</Link>
        </div>
      </section>

      <section className="section">
        <div className="section-cta">
          <h2>Готовы попробовать?</h2>
          <p>
            Скопируйте три ячейки в свой Kaggle-блокнот — через пару минут будет
            публичный ComfyUI на двух Tesla T4.
          </p>
          <div className="cta-buttons">
            <a className="btn btn-primary" href="https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU">
              Открыть на GitHub
            </a>
            <a className="btn btn-secondary" href="https://boosty.to/the_angel/donate">
              💖 Поддержать проект
            </a>
            <Link to="/news" className="btn btn-ghost">Лента обновлений</Link>
          </div>
        </div>
      </section>
    </>
  );
}
