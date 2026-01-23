"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getQuizSet,
  judgeAnswer,
  type ApiError,
  toApiError,
} from "@/lib/api";
import type { Citation } from "@/lib/types";

interface Quiz {
  id: string;
  statement: string;
  type: "true_false";
  answer_bool: boolean;
  explanation: string;
  citations: Citation[];
}

export default function QuizPlayPage() {
  const params = useParams();
  const router = useRouter();
  const quizSetId = params.id as string;

  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<boolean | null>(null);
  const [judgeResult, setJudgeResult] = useState<{
    is_correct: boolean;
    correct_answer: boolean;
    explanation: string;
    citations: Citation[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [judging, setJudging] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  // クイズセットを取得
  useEffect(() => {
    const fetchQuizSet = async () => {
      try {
        setLoading(true);
        const quizSet = await getQuizSet(quizSetId);
        setQuizzes(quizSet.quizzes);
      } catch (err) {
        const apiError = toApiError(err);
        setError(apiError);
      } finally {
        setLoading(false);
      }
    };

    if (quizSetId) {
      fetchQuizSet();
    }
  }, [quizSetId]);

  // 回答を判定
  const handleJudge = async (answer: boolean) => {
    if (!quizzes[currentIndex]) return;

    setJudging(true);
    setSelectedAnswer(answer);
    setJudgeResult(null);
    setError(null);

    try {
      // 既存のjudgeAnswer APIは1問形式なので、直接クイズデータから判定結果を構築
      const currentQuiz = quizzes[currentIndex];
      const isCorrect = answer === currentQuiz.answer_bool;

      setJudgeResult({
        is_correct: isCorrect,
        correct_answer: currentQuiz.answer_bool,
        explanation: currentQuiz.explanation,
        citations: currentQuiz.citations,
      });
    } catch (err) {
      const apiError = toApiError(err);
      setError(apiError);
    } finally {
      setJudging(false);
    }
  };

  // 次の問題へ
  const handleNext = () => {
    if (currentIndex < quizzes.length - 1) {
      setCurrentIndex(currentIndex + 1);
      setSelectedAnswer(null);
      setJudgeResult(null);
      setError(null);
    }
  };

  // 前の問題へ
  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
      setSelectedAnswer(null);
      setJudgeResult(null);
      setError(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-dvh bg-gray-50 py-6 sm:py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="text-center text-gray-500">読み込み中...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-dvh bg-gray-50 py-6 sm:py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="bg-red-50 border border-red-200 rounded-xl p-4">
            <div className="text-sm text-red-700">{error.message}</div>
            <button
              onClick={() => router.push("/quiz")}
              className="mt-4 text-sm text-blue-600 hover:text-blue-700"
            >
              クイズページに戻る
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (quizzes.length === 0) {
    return (
      <div className="min-h-dvh bg-gray-50 py-6 sm:py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="text-center text-gray-500">
            クイズが見つかりませんでした。
          </div>
        </div>
      </div>
    );
  }

  const currentQuiz = quizzes[currentIndex];
  const isLast = currentIndex === quizzes.length - 1;
  const isFirst = currentIndex === 0;

  return (
    <div className="min-h-dvh bg-gray-50 py-6 sm:py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">
            クイズプレイ
          </h1>
          <div className="text-sm text-gray-500">
            {currentIndex + 1} / {quizzes.length}
          </div>
        </div>

        <div className="space-y-6">
          {/* 問題文 */}
          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              問題 {currentIndex + 1}
            </h2>
            <div className="text-base text-gray-700 whitespace-pre-wrap break-words">
              {currentQuiz.statement}
            </div>
          </div>

          {/* 回答ボタン */}
          {!judgeResult && (
            <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => handleJudge(true)}
                  disabled={judging}
                  className={`h-16 rounded-xl border-2 font-medium text-lg transition-colors ${
                    selectedAnswer === true
                      ? "border-green-500 bg-green-50 text-green-700"
                      : "border-green-300 bg-white text-green-700 hover:bg-green-50"
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  ○
                </button>
                <button
                  onClick={() => handleJudge(false)}
                  disabled={judging}
                  className={`h-16 rounded-xl border-2 font-medium text-lg transition-colors ${
                    selectedAnswer === false
                      ? "border-red-500 bg-red-50 text-red-700"
                      : "border-red-300 bg-white text-red-700 hover:bg-red-50"
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  ×
                </button>
              </div>
            </div>
          )}

          {/* 判定結果 */}
          {judgeResult && (
            <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-900">
                判定結果
              </h2>
              <div className="space-y-3">
                <div>
                  <span className="text-sm font-medium text-gray-700">
                    正誤:{" "}
                  </span>
                  <span
                    className={`text-sm font-semibold ${
                      judgeResult.is_correct
                        ? "text-green-600"
                        : "text-red-600"
                    }`}
                  >
                    {judgeResult.is_correct ? "正解" : "不正解"}
                  </span>
                </div>
                <div>
                  <span className="text-sm font-medium text-gray-700">
                    正解:{" "}
                  </span>
                  <span className="text-sm text-gray-900">
                    {judgeResult.correct_answer ? "○" : "×"}
                  </span>
                </div>
                <div>
                  <span className="text-sm font-medium text-gray-700">
                    解説:{" "}
                  </span>
                  <div className="text-sm text-gray-700 whitespace-pre-wrap break-words mt-1">
                    {judgeResult.explanation}
                  </div>
                </div>
                {judgeResult.citations && judgeResult.citations.length > 0 && (
                  <div>
                    <span className="text-sm font-medium text-gray-700">
                      根拠:{" "}
                    </span>
                    <div className="space-y-2 mt-2">
                      {judgeResult.citations.map((citation, index) => (
                        <div
                          key={index}
                          className="p-3 bg-gray-50 rounded-xl border border-gray-100"
                        >
                          <div className="text-xs font-medium text-gray-500 mb-1">
                            {citation.source}
                            {citation.page !== null && ` (p.${citation.page})`}
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
            </div>
          )}

          {/* ナビゲーションボタン */}
          <div className="flex justify-between">
            <button
              onClick={handlePrev}
              disabled={isFirst}
              className="h-12 min-w-[120px] rounded-xl border border-gray-300 bg-white px-4 text-base font-medium text-gray-900 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              前の問題
            </button>
            {isLast ? (
              <button
                onClick={() => router.push("/quiz")}
                className="h-12 min-w-[120px] rounded-xl bg-blue-600 px-4 text-base font-medium text-white hover:bg-blue-700 transition-colors"
              >
                完了
              </button>
            ) : (
              <button
                onClick={handleNext}
                disabled={!judgeResult}
                className="h-12 min-w-[120px] rounded-xl bg-blue-600 px-4 text-base font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                次の問題
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
