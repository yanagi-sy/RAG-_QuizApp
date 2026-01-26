"use client";

/**
 * 難易度選択UI（beginner / intermediate / advanced）
 * 【初心者向け】ラジオ＋出題ボタン。useQuiz の level/setLevel と連動。
 * エラー時は再試行可能な場合のみ再試行ボタンを表示。
 */
import type { Level, ApiError } from "@/lib/types";

interface DifficultyPickerProps {
  level: Level;
  onLevelChange: (level: Level) => void;
  onStartQuiz: () => void;
  loading?: boolean;
  error: ApiError | null;
  onRetry?: () => void;
}

export default function DifficultyPicker({
  level,
  onLevelChange,
  onStartQuiz,
  loading = false,
  error,
  onRetry,
}: DifficultyPickerProps) {
  const handleStart = () => {
    onStartQuiz();
  };

  // NETWORK_ERROR / TIMEOUT / INTERNAL_ERROR の場合のみ再試行ボタンを表示
  // QUOTA_EXCEEDEDは時間が経たないと解決しないため、再試行ボタンは表示しない
  const isRetryable = 
    error && (
      error.code === "NETWORK_ERROR" || 
      error.code === "TIMEOUT" || 
      error.code === "INTERNAL_ERROR"
    ) && error.code !== "QUOTA_EXCEEDED";

  return (
    <div className="space-y-4">
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
        <div className="space-y-4">
          <label
            htmlFor="difficulty"
            className="block text-sm font-medium text-gray-700"
          >
            難易度
          </label>
          <select
            id="difficulty"
            value={level}
            onChange={(e) => onLevelChange(e.target.value as Level)}
            disabled={loading}
            className="w-full h-12 px-4 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-base bg-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="beginner">初級</option>
            <option value="intermediate">中級</option>
            <option value="advanced">上級</option>
          </select>
          <button
            onClick={handleStart}
            disabled={loading}
            className="w-full h-12 bg-blue-600 text-white font-medium rounded-xl shadow-sm hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "出題中…" : "出題"}
          </button>
        </div>
      </div>
      {error && (
        <div className="bg-white border border-red-200 rounded-2xl shadow-sm p-4 sm:p-6 space-y-4">
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
      )}
    </div>
  );
}
