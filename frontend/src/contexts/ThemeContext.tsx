'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { API_URL } from '@/utils/api';

type Theme = 'light' | 'dark' | 'system';

interface ThemeContextType {
  theme: Theme;
  resolvedTheme: 'light' | 'dark';
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('system');
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>('light');

  // Get system preference
  const getSystemTheme = (): 'light' | 'dark' => {
    if (typeof window !== 'undefined') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return 'light';
  };

  // Apply theme to document
  const applyTheme = (resolvedTheme: 'light' | 'dark') => {
    if (typeof document !== 'undefined') {
      const root = document.documentElement;
      if (resolvedTheme === 'dark') {
        root.classList.add('dark');
      } else {
        root.classList.remove('dark');
      }
    }
  };

  // Calculate resolved theme
  const calculateResolvedTheme = (theme: Theme): 'light' | 'dark' => {
    if (theme === 'system') {
      return getSystemTheme();
    }
    return theme;
  };

  // Load theme from localStorage and API on mount
  useEffect(() => {
    const loadTheme = async () => {
      // First, check localStorage for immediate theme application
      const storedTheme = localStorage.getItem('theme') as Theme | null;
      if (storedTheme && ['light', 'dark', 'system'].includes(storedTheme)) {
        setThemeState(storedTheme);
        const resolved = calculateResolvedTheme(storedTheme);
        setResolvedTheme(resolved);
        applyTheme(resolved);
      } else {
        // Apply default system theme
        const resolved = calculateResolvedTheme('system');
        setResolvedTheme(resolved);
        applyTheme(resolved);
      }

      // Then, try to fetch from API for persistence across devices
      try {
        const response = await fetch(`${API_URL}/api/config/settings/theme_mode`);
        if (response.ok) {
          const data = await response.json();
          const apiTheme = data.value as Theme;
          if (['light', 'dark', 'system'].includes(apiTheme)) {
            setThemeState(apiTheme);
            localStorage.setItem('theme', apiTheme);
            const resolved = calculateResolvedTheme(apiTheme);
            setResolvedTheme(resolved);
            applyTheme(resolved);
          }
        }
      } catch {
        // API not available, use localStorage/default
      }
    };

    loadTheme();
  }, []);

  // Listen for system theme changes
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      if (theme === 'system') {
        const resolved = getSystemTheme();
        setResolvedTheme(resolved);
        applyTheme(resolved);
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  // Set theme handler
  const setTheme = async (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem('theme', newTheme);
    const resolved = calculateResolvedTheme(newTheme);
    setResolvedTheme(resolved);
    applyTheme(resolved);

    // Save to API for persistence
    try {
      await fetch(`${API_URL}/api/config/settings/theme_mode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: newTheme }),
      });
    } catch {
      // API not available, localStorage will persist locally
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
