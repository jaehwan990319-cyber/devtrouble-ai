import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/Button';
import { ErrorBanner, Spinner } from '../components/Feedback';
import { Input } from '../components/FormField';
import { MarkdownPreview } from '../components/MarkdownPreview';
import { useAiSearchStream } from '../hooks/useAiSearch';
import type { AiCitation, ConversationMessage } from '../types/ai';

const STAGE_LABELS: Record<string, string> = {
  classify: '질문 분류 중...',
  retrieve: '관련 문서 검색 중...',
  rerank: '검색 결과 재정렬 중...',
  reformulate: '질문을 다시 정리하는 중...',
  generate: '답변 작성 중...',
  token: '답변 작성 중...',
  validate: '답변 검증 중...',
};

interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
  citations?: AiCitation[];
  onTopic?: boolean;
  isGrounded?: boolean;
}

function AssistantTurn({ turn }: { turn: ChatTurn }) {
  if (turn.onTopic === false) {
    return <p className="text-sm text-slate-600">{turn.content}</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {!turn.isGrounded && turn.isGrounded !== undefined && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          이 답변은 검색된 문서 내용과 완전히 일치하지 않을 수 있습니다. 참고용으로만 봐주세요.
        </div>
      )}
      <MarkdownPreview content={turn.content} />

      {turn.citations && turn.citations.length > 0 && (
        <div className="border-t border-slate-100 pt-3">
          <h3 className="mb-2 text-xs font-semibold text-slate-500">출처</h3>
          <ul className="flex flex-col gap-1.5">
            {turn.citations.map((citation) => (
              <li key={citation.document_id}>
                <Link
                  to={`/documents/${citation.document_id}`}
                  className="text-sm text-brand-600 hover:underline"
                >
                  {citation.title || citation.document_id}
                </Link>
                <span className="ml-2 text-xs text-slate-400">
                  관련도 {(citation.relevance_score * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function AiSearchPage() {
  const [query, setQuery] = useState('');
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const { run, stage, partialAnswer, isStreaming, error } = useAiSearchStream();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || isStreaming) return;

    const history: ConversationMessage[] = turns.map((t) => ({ role: t.role, content: t.content }));
    setTurns((prev) => [...prev, { role: 'user', content: trimmed }]);
    setQuery('');

    try {
      const response = await run({ query: trimmed, history });

      setTurns((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.answer,
          citations: response.citations,
          onTopic: response.on_topic,
          isGrounded: response.is_grounded,
        },
      ]);
    } catch {
      // error는 useAiSearchStream이 상태로 들고 있으므로 여기서는 턴만 롤백하지 않고 그대로 둔다.
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">AI 트러블슈팅 검색</h1>
        <p className="mt-1 text-sm text-slate-500">
          겪고 있는 문제를 자연어로 질문하면, 과거 트러블슈팅 기록을 근거로 원인과 해결 방법을 찾아드립니다.
          이어서 후속 질문도 할 수 있어요.
        </p>
      </div>

      {turns.length > 0 && (
        <div className="flex flex-col gap-4">
          {turns.map((turn, index) =>
            turn.role === 'user' ? (
              <div key={index} className="ml-auto max-w-[80%] rounded-lg bg-brand-500 px-4 py-2 text-sm text-white">
                {turn.content}
              </div>
            ) : (
              <div key={index} className="rounded-lg border border-slate-200 bg-white p-4">
                <AssistantTurn turn={turn} />
              </div>
            ),
          )}
        </div>
      )}

      {isStreaming && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner className="h-4 w-4" />
            {stage ? (STAGE_LABELS[stage] ?? stage) : '처리 중...'}
          </div>
          {partialAnswer && (
            <div className="mt-3 border-t border-slate-100 pt-3">
              <MarkdownPreview content={partialAnswer} />
            </div>
          )}
        </div>
      )}

      {error && <ErrorBanner message={error.message} />}

      <form onSubmit={(e) => void handleSubmit(e)} className="flex gap-2">
        <div className="flex-1">
          <Input
            placeholder="예: Redis 커넥션이 자꾸 끊기는데 원인이 뭘까?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={isStreaming}
          />
        </div>
        <Button type="submit" isLoading={isStreaming}>
          질문하기
        </Button>
      </form>
    </div>
  );
}
