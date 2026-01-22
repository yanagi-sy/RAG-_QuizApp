"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  listQuizSets,
  getQuizSet,
  deleteQuizSet,
  type ApiError,
  toApiError,
} from "@/lib/api";
import type { Citation } from "@/lib/types";

interface QuizSetMetadata {
  id: string;
  title: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  created_at: string;
  question_count: number;
}

interface Quiz {
  id: string;
  statement: string;
  type: "true_false";
  answer_bool: boolean;
  explanation: string;
  citations: Citation[];
}

export default function QuizManagePage() {
  const router = useRouter();
  const [quizSets, setQuizSets] = useState<QuizSetMetadata[]>([]);
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [selectedSetQuizzes, setSelectedSetQuizzes] = useState<Quiz[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  // クイズセットのリストを取得
  useEffect(() => {
    fetchQuizSets();
  }, []);

  const fetchQuizSets = async () => {
    try {
      setLoading(true);
      const result = await listQuizSets();
      setQuizSets(result.quiz_sets);
    } catch (err) {
      const apiError = toApiError(err);
      setError(apiError);
    } finally {
      setLoading(false);
    }
  };

  // クイズセットの詳細を取得
  const handleViewDetail = async (id: string) => {
    if (selectedSetId === id && selectedSetQuizzes.length > 0) {
      // 既に表示中の場合は閉じる
      setSelectedSetId(null);
      setSelectedSetQuizzes([]);
      return;
    }

    try {
      setLoadingDetail(true);
      setError(null);
      const quizSet = await getQuizSet(id);
      setSelectedSetId(id);
      setSelectedSetQuizzes(quizSet.quizzes);
    } catch (err) {
      const apiError = toApiError(err);
      setError(apiError);
    } finally {
      setLoadingDetail(false);
    }
  };

  // クイズセットを削除
  const handleDelete = async (id: string) => {
    if (!confirm("このクイズセットを削除しますか？")) {
      return;
    }

    try {
      setDeleting(id);
      await deleteQuizSet(id);
      // 削除成功時はリストを更新
      if (selectedSetId === id) {
        setSelectedSetId(null);
        setSelectedSetQuizzes([]);
      }
      await fetchQuizSets();
    } catch (err) {
      const apiError = toApiError(err);
      setError(apiError);
    } finally {
      setDeleting(null);
    }
  };

  // 難易度の表示名
  const getDifficultyLabel = (
    difficulty: "beginner" | "intermediate" | "advanced"
  ) => {
    const labels = {
      beginner: "初級",
      intermediate: "中級",
      advanced: "上級",
    };
    return labels[difficulty];
  };

  // 日時のフォーマット
  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleString("ja-JP", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateString;
    }
  };

  return (
    <div className="min-h-dvh bg-gray-50 py-6 sm:py-8">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">
            クイズ管理
          </h1>
          <button
            onClick={() => router.push("/quiz/generate")}
            className="h-12 min-w-[140px] rounded-xl bg-blue-600 px-4 text-base font-medium text-white hover:bg-blue-700 transition-colors"
          >
            新規生成
          </button>
        </div>

        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-xl p-4">
            <div className="text-sm text-red-700">{error.message}</div>
          </div>
        )}

        {loading ? (
          <div className="text-center text-gray-500">読み込み中...</div>
        ) : quizSets.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-8 text-center">
            <p className="text-gray-500 mb-4">クイズセットがありません。</p>
            <button
              onClick={() => router.push("/quiz/generate")}
              className="h-12 min-w-[140px] rounded-xl bg-blue-600 px-4 text-base font-medium text-white hover:bg-blue-700 transition-colors"
            >
              新規生成
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* クイズセットリスト */}
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900">
                クイズセット一覧 ({quizSets.length}件)
              </h2>
              <div className="space-y-3">
                {quizSets.map((set) => (
                  <div
                    key={set.id}
                    className={`bg-white border rounded-xl shadow-sm p-4 transition-colors ${
                      selectedSetId === set.id
                        ? "border-blue-500 bg-blue-50"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-medium text-gray-900 mb-1">
                          {set.title}
                        </h3>
                        <div className="flex items-center gap-3 text-sm text-gray-500">
                          <span>{getDifficultyLabel(set.difficulty)}</span>
                          <span>•</span>
                          <span>{set.question_count}問</span>
                          <span>•</span>
                          <span>{formatDate(set.created_at)}</span>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => router.push(`/quiz/play/${set.id}`)}
                        className="flex-1 h-9 rounded-lg bg-blue-600 px-3 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
                      >
                        プレイ
                      </button>
                      <button
                        onClick={() => handleViewDetail(set.id)}
                        disabled={loadingDetail}
                        className="flex-1 h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                      >
                        {selectedSetId === set.id ? "閉じる" : "詳細"}
                      </button>
                      <button
                        onClick={() => handleDelete(set.id)}
                        disabled={deleting === set.id}
                        className="h-9 w-9 rounded-lg border border-red-300 bg-white text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
                      >
                        {deleting === set.id ? "..." : "🗑"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* クイズセット詳細 */}
            {selectedSetId && (
              <div className="space-y-4">
                <h2 className="text-lg font-semibold text-gray-900">
                  クイズ内容
                </h2>
                {loadingDetail ? (
                  <div className="text-center text-gray-500">読み込み中...</div>
                ) : (
                  <div className="space-y-4 max-h-[calc(100vh-200px)] overflow-y-auto">
                    {selectedSetQuizzes.map((quiz, index) => (
                      <div
                        key={quiz.id}
                        className="bg-white border border-gray-200 rounded-xl shadow-sm p-4"
                      >
                        <div className="mb-3 flex items-center justify-between">
                          <span className="text-sm font-medium text-gray-700">
                            問題 {index + 1}
                          </span>
                          <span className="text-sm text-gray-500">
                            正解: {quiz.answer_bool ? "○" : "×"}
                          </span>
                        </div>
                        <div className="text-sm text-gray-900 mb-3">
                          {quiz.statement}
                        </div>
                        <div className="text-xs text-gray-600 mb-2">
                          解説: {quiz.explanation}
                        </div>
                        {quiz.citations && quiz.citations.length > 0 && (
                          <div className="mt-2 space-y-1">
                            {quiz.citations.map((citation, citIndex) => (
                              <div
                                key={citIndex}
                                className="text-xs text-gray-500 bg-gray-50 p-2 rounded"
                              >
                                <div className="font-medium">
                                  {citation.source}
                                  {citation.page !== null &&
                                    ` (p.${citation.page})`}
                                </div>
                                <div className="mt-1 line-clamp-2">
                                  {citation.quote}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
