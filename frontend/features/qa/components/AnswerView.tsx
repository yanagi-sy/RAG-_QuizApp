"use client";

import type { AskResponse, ApiError, Citation } from "@/lib/types";

interface AnswerViewProps {
  loading?: boolean;
  error: ApiError | null;
  result: AskResponse | null;
  onRetry?: () => void;
}

export default function AnswerView({
  loading,
  error,
  result,
  onRetry,
}: AnswerViewProps) {
  // ローディング中
  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
        <div className="text-gray-600 text-center py-4">取得中…</div>
      </div>
    );
  }

  // エラー時（INVALID_INPUTは除外 - AskFormで表示するため）
  if (error && error.code !== "INVALID_INPUT") {
    // NETWORK_ERROR / TIMEOUT / INTERNAL_ERROR の場合のみ再試行ボタンを表示
    const isRetryable = 
      error.code === "NETWORK_ERROR" || 
      error.code === "TIMEOUT" || 
      error.code === "INTERNAL_ERROR";
    
    return (
      <div className="bg-white border border-red-200 rounded-2xl shadow-sm p-4 sm:p-6 space-y-4">
        <h2 className="text-lg font-semibold text-red-900">エラー</h2>
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 whitespace-pre-wrap break-words">
          {error.message}
        </div>
        {isRetryable && onRetry && (
          <button
            onClick={onRetry}
            className="w-full sm:w-auto h-12 min-w-[140px] rounded-xl border border-gray-300 bg-white px-4 text-base font-medium text-gray-900 hover:bg-zinc-50 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            再試行
          </button>
        )}
      </div>
    );
  }

  // 結果がない場合は何も表示しない
  if (!result) {
    return null;
  }

  // 成功時：回答とcitationsを表示
  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">回答</h2>
        <div className="text-gray-700 whitespace-pre-wrap break-words">
          {result.answer}
        </div>
      </div>

      {result.citations && result.citations.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">
            根拠（最大5件）
          </h2>
          <div className="space-y-3">
            {result.citations.slice(0, 5).map((citation: Citation, index: number) => (
              <div
                key={index}
                className="p-3 bg-gray-50 rounded-xl border border-gray-100"
              >
                <div className="text-xs font-medium text-gray-500 mb-1">
                  {citation.source} (p.{citation.page})
                </div>
                <div className="text-sm text-gray-700 whitespace-pre-wrap break-words">
                  {citation.quote}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
