import { Link } from 'react-router-dom';

export function Footer() {
  return (
    <footer className="footer" role="contentinfo">
      <div className="footer-inner">
        <div className="footer-brand">
          <strong>THE ANGEL AI</strong>
          <span className="muted">сделано с ❤️ для тех, у кого нет своего GPU</span>
        </div>
        <nav className="footer-nav" aria-label="Социальные ссылки">
          <a href="https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
          <a href="https://vk.com/theangel_lab" target="_blank" rel="noopener noreferrer">
            ВКонтакте
          </a>
          <a href="https://boosty.to/the_angel/donate" target="_blank" rel="noopener noreferrer">
            Boosty
          </a>
          <Link to="/news">Лента</Link>
        </nav>
      </div>
    </footer>
  );
}
