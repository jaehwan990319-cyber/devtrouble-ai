import type { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/Button';
import { useAuth } from '../store/AuthContext';

export function MainLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate('/login');
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-bold text-brand-600">
            DevTrouble AI
          </Link>

          {user && (
            <nav className="flex items-center gap-4 text-sm">
              <Link to="/projects" className="text-slate-600 hover:text-brand-600">
                프로젝트
              </Link>
              <Link to="/documents" className="text-slate-600 hover:text-brand-600">
                문서 목록
              </Link>
              <Link to="/ai-search" className="text-slate-600 hover:text-brand-600">
                AI 검색
              </Link>
              <Link to="/my-activity" className="text-slate-600 hover:text-brand-600">
                내 활동
              </Link>
              <Link
                to="/documents/new"
                className="rounded-md bg-brand-500 px-3 py-1.5 text-white hover:bg-brand-600"
              >
                + 새 문서
              </Link>
              <span className="text-slate-400">|</span>
              <span className="text-slate-600">{user.nickname}님</span>
              <Button variant="ghost" onClick={() => void handleLogout()}>
                로그아웃
              </Button>
            </nav>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}
