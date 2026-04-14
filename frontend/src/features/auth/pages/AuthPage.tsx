import { FormEvent, useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { ApiError } from '@/shared/api/errors';
import { useAuthSession } from '@/app/providers/AuthSessionProvider';
import { Panel } from '@/shared/ui/Panel';
import { TextField } from '@/shared/ui/Field';
import { Button } from '@/shared/ui/Button';

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Не удалось выполнить auth-запрос.';
}

export function AuthPage() {
  const { status, signInWithPassword, signUpWithPassword } = useAuthSession();
  const [mode, setMode] = useState<'sign_in' | 'sign_up'>('sign_in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const title = useMemo(() => (mode === 'sign_in' ? 'Sign in' : 'Create account'), [mode]);

  if (status === 'authenticated') {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      if (mode === 'sign_in') {
        await signInWithPassword({ email, password });
      } else {
        await signUpWithPassword({ email, password, displayName });
      }
    } catch (error) {
      setSubmitError(errorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="content-stack" style={{ maxWidth: 560, margin: '40px auto' }}>
      <Panel title="Security baseline auth" description="Веб-клиент больше не опирается на X-User-Id как основной режим. Вход идет через server session + refresh cookie + short-lived bearer.">
        <div className="toolbar">
          <Button variant={mode === 'sign_in' ? 'primary' : 'default'} onClick={() => setMode('sign_in')}>
            Sign in
          </Button>
          <Button variant={mode === 'sign_up' ? 'primary' : 'default'} onClick={() => setMode('sign_up')}>
            Sign up
          </Button>
        </div>
      </Panel>

      <Panel title={title} description="После входа access token хранится только в памяти вкладки, а refresh cookie ротируется сервером.">
        <form className="stack" onSubmit={onSubmit}>
          <TextField label="Email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <TextField label="Password" type="password" autoComplete={mode === 'sign_in' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} required />
          {mode === 'sign_up' ? (
            <TextField label="Display name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
          ) : null}

          {submitError ? <p className="error-text">{submitError}</p> : null}

          <div className="toolbar">
            <Button type="submit" variant="primary" disabled={isSubmitting}>
              {isSubmitting ? 'Working…' : mode === 'sign_in' ? 'Sign in' : 'Create account'}
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
