import { NavLink, Link } from 'react-router-dom';

export function Nav() {
  return (
    <nav className="nav" role="navigation" aria-label="Главная навигация">
      <Link to="/" className="nav-brand">
        <span className="dot" aria-hidden="true" />
        THE&nbsp;ANGEL&nbsp;AI
      </Link>
      <div className="nav-links">
        <NavLink to="/#project" className={({ isActive }) => (isActive ? 'is-active' : '')}>
          Проект
        </NavLink>
        <NavLink to="/#start" className={({ isActive }) => (isActive ? 'is-active' : '')}>
          Старт
        </NavLink>
        <NavLink to="/#updates" className={({ isActive }) => (isActive ? 'is-active' : '')}>
          Новости
        </NavLink>
        <NavLink to="/news" className={({ isActive }) => (isActive ? 'is-active' : '')}>
          Лента →
        </NavLink>
      </div>
    </nav>
  );
}
