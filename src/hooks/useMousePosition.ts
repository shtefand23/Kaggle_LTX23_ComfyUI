import { useEffect, useState, useRef } from 'react';

export interface MousePosition {
  x: number; // 0..100 (%)
  y: number; // 0..100 (%)
}

/**
 * Отслеживает позицию мыши в процентах от viewport.
 * Используется для mouse-tracking spotlight в Hero.
 *
 * Throttled через requestAnimationFrame — не триггерит re-render
 * на каждое событие mousemove (что приводит к 60+ fps re-renders
 * если mouse активно движется — нам это не нужно).
 */
export function useMousePosition(): MousePosition {
  const [pos, setPos] = useState<MousePosition>({ x: 50, y: 50 });
  const rafRef = useRef<number | null>(null);
  const pendingRef = useRef<MousePosition | null>(null);

  useEffect(() => {
    const handle = (e: MouseEvent) => {
      const x = (e.clientX / window.innerWidth) * 100;
      const y = (e.clientY / window.innerHeight) * 100;
      pendingRef.current = { x, y };
      if (rafRef.current === null) {
        rafRef.current = requestAnimationFrame(() => {
          if (pendingRef.current) setPos(pendingRef.current);
          rafRef.current = null;
        });
      }
    };
    window.addEventListener('mousemove', handle, { passive: true });
    return () => {
      window.removeEventListener('mousemove', handle);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return pos;
}
