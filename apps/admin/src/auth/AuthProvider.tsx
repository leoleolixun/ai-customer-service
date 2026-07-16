import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api } from '@/api/client';
import type { AdminMe } from '@/api/types';

interface LoginInput {
  email: string;
  password: string;
  tenantId: string;
}

interface AuthContextValue {
  user: AdminMe | null;
  checking: boolean;
  login: (input: LoginInput) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [user, setUser] = useState<AdminMe | null>(null);
  const [checking, setChecking] = useState(true);

  const loadMe = useCallback(async () => {
    try {
      setUser(await api<AdminMe>('/v1/admin/me'));
    } catch {
      localStorage.removeItem('support-admin-token');
      setUser(null);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    if (localStorage.getItem('support-admin-token')) void loadMe();
    else setChecking(false);
  }, [loadMe]);

  useEffect(() => {
    const expire = () => setUser(null);
    window.addEventListener('support-auth-expired', expire);
    return () => window.removeEventListener('support-auth-expired', expire);
  }, []);

  const login = useCallback(async (input: LoginInput) => {
    const token = await api<{ access_token: string }>('/v1/admin/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email: input.email,
        password: input.password,
        tenant_id: input.tenantId || null,
      }),
    });
    localStorage.setItem('support-admin-token', token.access_token);
    setUser(await api<AdminMe>('/v1/admin/me'));
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('support-admin-token');
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, checking, login, logout }), [checking, login, logout, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
