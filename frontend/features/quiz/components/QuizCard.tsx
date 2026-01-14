"use client";

interface QuizCardProps {
  question: string | null;
  loading?: boolean;
}

export default function QuizCard({ question, loading = false }: QuizCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-3">問題</h2>
      {loading ? (
        <div className="text-gray-600">取得中…</div>
      ) : question ? (
        <div className="text-gray-700 whitespace-pre-wrap break-words">
          {question}
        </div>
      ) : (
        <div className="text-gray-500">未出題</div>
      )}
    </div>
  );
}
