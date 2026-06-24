import { useEffect, useState } from 'react';

/**
 * Возвращает true если пользователь выбрал `prefers-reduced-motion: reduce`.
 * Нужно для отключения интерактивных анимаций в Hero (mouse parallax, glitch).
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mqj = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handle = () => setReduced(mqj.matches);
    handle();
    mqj.addEventListener('change', handle);
    return () => mqj.removeEventListener('change', handle);
  }, []);

  return reduced;
}
