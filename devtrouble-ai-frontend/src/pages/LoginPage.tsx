import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from '../components/Button';
import { Input } from '../components/FormField';
import { ErrorBanner } from '../components/Feedback';
import { useAuth } from '../store/AuthContext';
import { ApiError } from '../types/api';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login({ email, password });
      const redirectTo = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/documents';
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '로그인에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-sm">
      <h1 className="mb-6 text-center text-2xl font-bold text-slate-900">DevTrouble AI 로그인</h1>

      <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        {error && <ErrorBanner message={error} />}

        <Input
          id="email"
          label="이메일"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          id="password"
          label="비밀번호"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <Button type="submit" isLoading={isSubmitting} className="mt-2">
          로그인
        </Button>
      </form>

      <p className="mt-4 text-center text-sm text-slate-500">
        계정이 없으신가요?{' '}
        <Link to="/signup" className="font-medium text-brand-600 hover:underline">
          회원가입
        </Link>
      </p>
    </div>
  );
}
