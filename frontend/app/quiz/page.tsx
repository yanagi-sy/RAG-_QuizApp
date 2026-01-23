"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  getAvailableSources,
  generateQuizSet,
  listQuizSets,
  getQuizSet,
  deleteQuizSet,
  type ApiError,
  toApiError,
} from "@/lib/api";
import type { Citation } from "@/lib/types";

type Level = "beginner" | "intermediate" | "advanced";

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

type Tab = "generate" | "manage";

export default function QuizPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>("generate");

  // クイズ生成用の状態
  const [sources, setSources] = useState<string[]>([]);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [level, setLevel] = useState<Level>("beginner");
  const [loadingGenerate, setLoadingGenerate] = useState(false);
  const [loadingSources, setLoadingSources] = useState(true);
  const [generateError, setGenerateError] = useState<ApiError | null>(null);

  // クイズ管理用の状態
  const [quizSets, setQuizSets] = useState<QuizSetMetadata[]>([]);
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [selectedSetQuizzes, setSelectedSetQuizzes] = useState<Quiz[]>([]);
  const [loadingManage, setLoadingManage] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [manageError, setManageError] = useState<ApiError | null>(null);

  // ソースファイルのリストを取得
  useEffect(() => {
    if (activeTab === "generate") {
      const fetchSources = async () => {
        try {
          setLoadingSources(true);
          const sourcesList = await getAvailableSources();
          setSources(sourcesList);
        } catch (err) {
          const apiError = toApiError(err);
          setGenerateError(apiError);
        } finally {
          setLoadingSources(false);
        }
      };

      fetchSources();
    }
  }, [activeTab]);

  // クイズセットのリストを取得
  useEffect(() => {
    if (activeTab === "manage") {
      fetchQuizSets();
    }
  }, [activeTab]);

  const fetchQuizSets = async () => {
    try {
      setLoadingManage(true);
      const result = await listQuizSets();
      setQuizSets(result.quiz_sets);
    } catch (err) {
      const apiError = toApiError(err);
      setManageError(apiError);
    } finally {
      setLoadingManage(false);
    }
  };

  // クイズ生成
  const handleGenerate = async () => {
    // 【品質担保】単一ソースが選択されていることを確認
    if (!selectedSource) {
      setGenerateError(
        new ApiError(
          "INVALID_INPUT",
          "ファイルを1件選択してください。"
        )
      );
      return;
    }

    setLoadingGenerate(true);
    setGenerateError(null);

    try {
      const result = await generateQuizSet(
        level,
        [selectedSource] // 単一ソースを配列で渡す
      );

      if (result.quizzes && result.quizzes.length > 0) {
        if (result.quiz_set_id) {
          // 生成成功時は管理タブに切り替えてリストを更新
          setActiveTab("manage");
          await fetchQuizSets();
          // プレイページに遷移
          router.push(`/quiz/play/${result.quiz_set_id}`);
        } else {
          setGenerateError(
            new ApiError(
              "INTERNAL_ERROR",
              `クイズは${result.quizzes.length}問生成されましたが、保存に失敗しました。`
            )
          );
        }
      } else {
        setGenerateError(
          new ApiError(
            "INTERNAL_ERROR",
            "クイズが生成されませんでした。別のファイルや難易度を試してください。"
          )
        );
      }
    } catch (err) {
      const apiError = toApiError(err);
      setGenerateError(apiError);
    } finally {
      setLoadingGenerate(false);
    }
  };

  // ソース選択（単一選択）
  const selectSource = (source: string) => {
    setSelectedSource(source);
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
      setManageError(null);
      const quizSet = await getQuizSet(id);
      setSelectedSetId(id);
      setSelectedSetQuizzes(quizSet.quizzes);
    } catch (err) {
      const apiError = toApiError(err);
      setManageError(apiError);
    } finally {
      setLoadingDetail(false);
    }
  };

  // クイズセットを削除（ワンクリックで削除）
  const handleDelete = async (id: string) => {
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
      setManageError(apiError);
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
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-6 sm:mb-8">
          クイズ
        </h1>

        {/* タブ */}
        <div className="mb-6 border-b border-gray-200">
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab("generate")}
              className={`px-4 py-2 text-base font-medium transition-colors border-b-2 ${
                activeTab === "generate"
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              クイズ生成
            </button>
            <button
              onClick={() => setActiveTab("manage")}
              className={`px-4 py-2 text-base font-medium transition-colors border-b-2 ${
                activeTab === "manage"
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              クイズ管理
            </button>
          </div>
        </div>

        {/* クイズ生成タブ */}
        {activeTab === "generate" && (
          <div className="space-y-6">
            {/* ファイル選択 */}
            <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                ファイル選択（必須）
              </h2>
              {loadingSources ? (
                <div className="text-sm text-gray-500">読み込み中...</div>
              ) : sources.length === 0 ? (
                <div className="text-sm text-gray-500">
                  利用可能なファイルがありません。
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="text-sm text-gray-700">
                    1件のファイルを選択してください
                  </div>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {sources.map((source) => (
                      <label
                        key={source}
                        className="flex items-center space-x-3 p-3 rounded-lg hover:bg-gray-50 cursor-pointer border border-transparent hover:border-gray-200 transition-colors"
                      >
                        <input
                          type="radio"
                          name="source"
                          value={source}
                          checked={selectedSource === source}
                          onChange={() => selectSource(source)}
                          className="w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                        />
                        <span className="text-sm text-gray-900">{source}</span>
                      </label>
                    ))}
                  </div>
                  {!selectedSource && (
                    <p className="text-xs text-red-600">
                      ※ ファイルを1件選択してください
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* 難易度選択 */}
            <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                難易度選択
              </h2>
              <div className="grid grid-cols-3 gap-4">
                {(
                  [
                    { value: "beginner", label: "初級" },
                    { value: "intermediate", label: "中級" },
                    { value: "advanced", label: "上級" },
                  ] as const
                ).map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setLevel(option.value)}
                    className={`h-12 rounded-xl border-2 font-medium transition-colors ${
                      level === option.value
                        ? "border-blue-500 bg-blue-50 text-blue-700"
                        : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {/* エラー表示 */}
            {generateError && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                <div className="text-sm text-red-700">{generateError.message}</div>
              </div>
            )}

            {/* 生成ボタン */}
            <div className="flex justify-end">
              <button
                onClick={handleGenerate}
                disabled={loadingGenerate || loadingSources || !selectedSource}
                className="h-12 min-w-[140px] rounded-xl bg-blue-600 px-6 text-base font-medium text-white hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              >
                {loadingGenerate ? "生成中..." : "生成"}
              </button>
            </div>
          </div>
        )}

        {/* クイズ管理タブ */}
        {activeTab === "manage" && (
          <div>
            {manageError && (
              <div className="mb-6 bg-red-50 border border-red-200 rounded-xl p-4">
                <div className="text-sm text-red-700">{manageError.message}</div>
              </div>
            )}

            {loadingManage ? (
              <div className="text-center text-gray-500">読み込み中...</div>
            ) : quizSets.length === 0 ? (
              <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-8 text-center">
                <p className="text-gray-500 mb-4">クイズセットがありません。</p>
                <button
                  onClick={() => setActiveTab("generate")}
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
        )}
      </div>
    </div>
  );
}
