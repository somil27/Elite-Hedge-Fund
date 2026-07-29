import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api from './api';

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  setToken: (token: string) => void;
  setUser: (user: AuthUser) => void;
  logout: () => void;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isAuthenticated: false,

      setToken: (token) => {
        set({ token, isAuthenticated: !!token });
      },

      setUser: (user) => {
        set({ user });
      },

      logout: () => {
        set({ token: null, user: null, isAuthenticated: false });
      },

      fetchUser: async () => {
        const { token, logout } = get();
        if (!token) return;

        try {
          // We assume api.ts has an interceptor that attaches the token
          const res = await api.get('/auth/me');
          set({ user: res.data });
        } catch (error) {
          console.error('Failed to fetch user:', error);
          logout(); // Invalid token, clear state
        }
      },
    }),
    {
      name: 'alphadesk-auth', // Saves to localStorage automatically
      partialize: (state) => ({ token: state.token }), // Only persist the token
    }
  )
);
