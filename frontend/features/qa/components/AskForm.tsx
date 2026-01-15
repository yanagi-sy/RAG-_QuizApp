"use client";

import { useState } from "react";
import type { ApiError } from "@/lib/types";

interface AskFormProps {
  onSubmit: (question: string) => void;
  loading?: boolean;
  apiError: ApiError | null;
}

export default function AskForm({ onSubmit, loading = false, apiError }: AskFormProps) {
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const trimmedQuestion = question.trim();
    
    if (!trimmedQuestion) {
      setError("質問を入力してください");
      return;
    }

    setError(null);
    onSubmit(trimmedQuestion);
  };

  // INVALID_INPUTエラーを表示（再試行ボタンは出さない）
  const invalidInputError = apiError && apiError.code === "INVALID_INPUT" ? apiError : null;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label
          htmlFor="question"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          質問
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => {
            setQuestion(e.target.value);
            if (error) setError(null);
          }}
          rows={6}
          className="w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none text-base text-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
          placeholder="質問を入力してください..."
          disabled={loading}
        />
      </div>
      {(error || invalidInputError) && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 whitespace-pre-wrap break-words">
          {error || (invalidInputError ? invalidInputError.message : "")}
        </div>
      )}
      <button
        type="submit"
        disabled={loading}
        className="w-full h-12 bg-blue-600 text-white font-medium rounded-xl shadow-sm hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? "送信中…" : "送信"}
      </button>
    </form>
  );
}
