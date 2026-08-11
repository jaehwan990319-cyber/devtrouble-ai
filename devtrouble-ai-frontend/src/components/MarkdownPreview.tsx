import ReactMarkdown from 'react-markdown';

export function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="markdown-body text-sm text-slate-800">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
