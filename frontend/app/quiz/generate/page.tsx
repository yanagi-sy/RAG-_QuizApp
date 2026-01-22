"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  getAvailableSources,
  generateQuizSet,
  type ApiError,
  toApiError,
} from "@/lib/api";

type Level = "beginner" | "intermediate" | "advanced";

export default function QuizGeneratePage() {
  const router = useRouter();
  const [sources, setSources] = useState<string[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [level, setLevel] = useState<Level>("beginner");
  const [loading, setLoading] = useState(false);
  const [loadingSources, setLoadingSources] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  // ソースファイルのリストを取得
  useEffect(() => {
    const fetchSources = async () => {
      try {
        setLoadingSources(true);
        const sourcesList = await getAvailableSources();
        setSources(sourcesList);
      } catch (err) {
        const apiError = toApiError(err);
        setError(apiError);
      } finally {
        setLoadingSources(false);
      }
    };

    fetchSources();
  }, []);

  // クイズ生成
  const handleGenerate = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await generateQuizSet(
        level,
        selectedSources.length > 0 ? selectedSources : undefined
      );

      // デバッグ情報をログに出力
      console.log("クイズ生成結果:", result);

      if (result.quizzes && result.quizzes.length > 0) {
        if (result.quiz_set_id) {
          // 生成成功時はプレイページに遷移
          router.push(`/quiz/play/${result.quiz_set_id}`);
        } else {
          setError(
            new ApiError(
              "INTERNAL_ERROR",
              `クイズは${result.quizzes.length}問生成されましたが、保存に失敗しました。`
            )
          );
        }
      } else {
        setError(
          new ApiError(
            "INTERNAL_ERROR",
            "クイズが生成されませんでした。別のファイルや難易度を試してください。"
          )
        );
      }
    } catch (err) {
      const apiError = toApiError(err);
      setError(apiError);
    } finally {
      setLoading(false);
    }
  };

  // ソース選択のトグル
  const toggleSource = (source: string) => {
    setSelectedSources((prev) =>
      prev.includes(source)
        ? prev.filter((s) => s !== source)
        : [...prev, source]
    );
  };

  // 全選択/全解除
  const toggleAllSources = () => {
    if (selectedSources.length === sources.length) {
      setSelectedSources([]);
    } else {
      setSelectedSources([...sources]);
    }
  };

  return (
    <div className="min-h-dvh bg-gray-50 py-6 sm:py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-6 sm:mb-8">
          クイズ生成
        </h1>

        <div className="space-y-6">
          {/* ファイル選択 */}
          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              ファイル選択
            </h2>
            {loadingSources ? (
              <div className="text-sm text-gray-500">読み込み中...</div>
            ) : sources.length === 0 ? (
              <div className="text-sm text-gray-500">
                利用可能なファイルがありません。
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-700">
                    {selectedSources.length} / {sources.length} 件選択中
                  </span>
                  <button
                    onClick={toggleAllSources}
                    className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                  >
                    {selectedSources.length === sources.length
                      ? "全解除"
                      : "全選択"}
                  </button>
                </div>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {sources.map((source) => (
                    <label
                      key={source}
                      className="flex items-center space-x-3 p-3 rounded-lg hover:bg-gray-50 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedSources.includes(source)}
                        onChange={() => toggleSource(source)}
                        className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-900">{source}</span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-gray-500">
                  ※ 未選択の場合は全ファイルから生成します
                </p>
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
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <div className="text-sm text-red-700">{error.message}</div>
            </div>
          )}

          {/* 生成ボタン */}
          <div className="flex justify-end">
            <button
              onClick={handleGenerate}
              disabled={loading || loadingSources}
              className="h-12 min-w-[140px] rounded-xl bg-blue-600 px-6 text-base font-medium text-white hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            >
              {loading ? "生成中..." : "5問生成"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
