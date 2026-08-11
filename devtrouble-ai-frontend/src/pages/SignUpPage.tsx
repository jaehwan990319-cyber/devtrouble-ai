import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/Button';
import { Input } from '../components/FormField';
import { ErrorBanner } from '../components/Feedback';
import { useAuth } from '../store/AuthContext';
import { ApiError } from '../types/api';

export function SignUpPage() {
  const { signUp } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError('비밀번호는 8자 이상이어야 합니다.');
      return;
    }

    setIsSubmitting(true);
    try {
      await signUp({ email, password, nickname });
      navigate('/documents', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '회원가입에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-sm">
      <h1 className="mb-6 text-center text-2xl font-bold text-slate-900">회원가입</h1>

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
          id="nickname"
          label="닉네임"
          type="text"
          required
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
        />
        <Input
          id="password"
          label="비밀번호 (8자 이상)"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <Button type="submit" isLoading={isSubmitting} className="mt-2">
          가입하기
        </Button>
      </form>

      <p className="mt-4 text-center text-sm text-slate-500">
        이미 계정이 있으신가요?{' '}
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          로그인
        </Link>
      </p>
    </div>
  );
}
