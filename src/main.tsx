import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import './styles/globals.css';
import './styles/hero.css';
import './styles/components.css';

// --- GitHub Pages SPA-fallback bootstrap ---
// 404.html (см. public/404.html) сохраняет в sessionStorage путь, на который
// пришёл пользователь напрямую (например /news), и редиректит на /. Здесь мы
// ДО монтирования React Router восстанавливаем исходный путь через
// history.replaceState, чтобы BrowserRouter проинициализировался уже на нём
// — и пользователь увидел /news, а не редирект на главную.
function bootstrapSpaRedirect(): void {
  try {
    const stored = sessionStorage.getItem('spa-redirect');
    if (!stored) return;
    sessionStorage.removeItem('spa-redirect');
    // Защита: принимаем только абсолютные пути внутри репо, без scheme/protocol-relative/backslash.
    if (!stored.startsWith('/') || stored.startsWith('//') || stored.startsWith('/\\')) return;
    const target = new URL(stored, window.location.origin);
    if (target.pathname !== window.location.pathname) {
      window.history.replaceState(
        window.history.state,
        '',
        target.pathname + target.search + target.hash,
      );
    }
  } catch {
    // sessionStorage / history могут быть недоступны (приватный режим, file://) — игнор.
  }
}
bootstrapSpaRedirect();

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('#root element not found in index.html');
}

// import.meta.env.BASE_URL — Vite-инжектированное значение из vite.config.ts (`base`).
// Происходит '/Kaggle_Workspace_FreeGPU/' на GH Pages, '/' на dev. BrowserRouter
// нарезает этот префикс перед матчингом <Route path="..."> — без него
// `<Route path="/news">` НЕ матчится на /Kaggle_Workspace_FreeGPU/news, и
// пользователь видит Home вместо News.
const basename = import.meta.env.BASE_URL;

createRoot(rootEl).render(
  <StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </StrictMode>
);
