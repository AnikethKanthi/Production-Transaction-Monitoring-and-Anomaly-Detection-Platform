import {
  createContext, useCallback, useContext, useEffect, useState, type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiGet, setBearerToken } from './api/client';

interface User {
  username: string;
  role: 'operator' | 'administrator';
}
const AuthContext = createContext<{ user: User | null; signOut: () => void }>({
  user: null,
  signOut: () => {},
});
export const useAuth = () => useContext(AuthContext);

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const client = useQueryClient();
  const signOut = useCallback(() => {
    setBearerToken(null);
    setUser(null);
    client.clear();
  }, [client]);
  useEffect(() => {
    const expired = () => {
      signOut();
      setError('Your session is no longer authorized. Sign in again.');
    };
    window.addEventListener('auth-expired', expired);
    return () => window.removeEventListener('auth-expired', expired);
  }, [signOut]);
  if (!user) return (
    <main className="login-shell">
      <section className="panel" aria-labelledby="sign-in-title">
        <h1 id="sign-in-title">Sign in to monitoring</h1>
        <p>
          Use the access token issued by your administrator.
          Your role is assigned by the service.
        </p>
        <form className="action-form" onSubmit={async (event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const token = String(new FormData(form).get('token') || '').trim();
          if (pending) return;
          setPending(true);
          setError('');
          setBearerToken(token);
          form.reset();
          try {
            const identity = await apiGet<User>('/auth/me');
            if (
              typeof identity.username !== 'string' || !identity.username ||
              !['operator', 'administrator'].includes(identity.role)
            ) throw new Error('Invalid authentication response');
            client.clear();
            setUser(identity);
          } catch {
            setBearerToken(null);
            setError('Sign-in failed. Check your token or try again when the service is available.');
          } finally {
            setPending(false);
          }
        }}>
          <label>
            Access token
            <input name="token" type="password" required minLength={32}
              maxLength={256} autoComplete="off" spellCheck={false} />
          </label>
          <button className="button" type="submit" disabled={pending}>
            {pending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        {error && <p role="alert">{error}</p>}
        <p>Tokens stay in memory. Refreshing or closing this page signs you out.</p>
      </section>
    </main>
  );
  return <AuthContext.Provider value={{user, signOut}}>{children}</AuthContext.Provider>;
}
