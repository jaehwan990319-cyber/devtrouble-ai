import { Navigate, Route, Routes } from 'react-router-dom';
import { ProtectedRoute } from './components/ProtectedRoute';
import { MainLayout } from './layouts/MainLayout';
import { AiSearchPage } from './pages/AiSearchPage';
import { DocumentDetailPage } from './pages/DocumentDetailPage';
import { DocumentFormPage } from './pages/DocumentFormPage';
import { DocumentListPage } from './pages/DocumentListPage';
import { LoginPage } from './pages/LoginPage';
import { MyActivityPage } from './pages/MyActivityPage';
import { ProjectListPage } from './pages/ProjectListPage';
import { SignUpPage } from './pages/SignUpPage';

export default function App() {
  return (
    <MainLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/documents" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignUpPage />} />

        <Route
          path="/my-activity"
          element={
            <ProtectedRoute>
              <MyActivityPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/projects"
          element={
            <ProtectedRoute>
              <ProjectListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/documents"
          element={
            <ProtectedRoute>
              <DocumentListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/documents/new"
          element={
            <ProtectedRoute>
              <DocumentFormPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/documents/:documentId"
          element={
            <ProtectedRoute>
              <DocumentDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/documents/:documentId/edit"
          element={
            <ProtectedRoute>
              <DocumentFormPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/ai-search"
          element={
            <ProtectedRoute>
              <AiSearchPage />
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<Navigate to="/documents" replace />} />
      </Routes>
    </MainLayout>
  );
}
