"use client";

import DifficultyPicker from "./components/DifficultyPicker";
import QuizCard from "./components/QuizCard";
import JudgeButtons from "./components/JudgeButtons";
import { useQuiz } from "./useQuiz";
import type { Citation } from "@/lib/types";

export default function QuizPage() {
  const {
    level,
    setLevel,
    quizId,
    question,
    loadingGenerate,
    loadingJudge,
    generateError,
    judgeError,
    judgeResult,
    generateQuiz,
    retryGenerate,
    regenerateQuiz,
    judge,
    retryJudge,
  } = useQuiz();

  const handleJudge = (answer: boolean) => {
    judge(answer);
  };

  const handleRetryJudge = () => {
    retryJudge();
  };

  const handleRegenerateQuiz = () => {
    regenerateQuiz();
  };

  return (
    <div className="min-h-dvh bg-gray-50 py-6 sm:py-8">
      <div className="max-w-5xl mx-auto px-4 sm:px-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-6 sm:mb-8">
          クイズ（○×）
        </h1>

        <div className="space-y-6">
          <DifficultyPicker
            level={level}
            onLevelChange={setLevel}
            onStartQuiz={generateQuiz}
            loading={loadingGenerate}
            error={generateError}
            onRetry={retryGenerate}
          />

          <QuizCard question={question} loading={loadingGenerate} />

          <JudgeButtons
            onJudge={handleJudge}
            disabled={!quizId || loadingJudge}
            loading={loadingJudge}
          />

          {(judgeError || judgeResult) && (
            <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-900">判定結果</h2>
              {judgeError ? (
                <div className="space-y-4">
                  <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 whitespace-pre-wrap break-words">
                    {judgeError.message}
                  </div>
                  {judgeError.code === "NOT_FOUND" ? (
                    <button
                      onClick={handleRegenerateQuiz}
                      className="w-full sm:w-auto h-12 min-w-[140px] rounded-xl border border-gray-300 bg-white px-4 text-base font-medium text-gray-900 hover:bg-zinc-50 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                    >
                      再出題
                    </button>
                  ) : (judgeError.code === "NETWORK_ERROR" || judgeError.code === "TIMEOUT" || judgeError.code === "INTERNAL_ERROR") ? (
                    <button
                      onClick={handleRetryJudge}
                      className="w-full sm:w-auto h-12 min-w-[140px] rounded-xl border border-gray-300 bg-white px-4 text-base font-medium text-gray-900 hover:bg-zinc-50 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                    >
                      再試行
                    </button>
                  ) : null}
                  {/* INVALID_INPUT の場合はボタンなし（表示のみ） */}
                </div>
              ) : judgeResult ? (
                <div className="space-y-3">
                  <div>
                    <span className="text-sm font-medium text-gray-700">正誤: </span>
                    <span className="text-sm text-gray-900">
                      {judgeResult.is_correct ? "正解" : "不正解"}
                    </span>
                  </div>
                  <div>
                    <span className="text-sm font-medium text-gray-700">解説: </span>
                    <div className="text-sm text-gray-700 whitespace-pre-wrap break-words mt-1">
                      {judgeResult.explanation}
                    </div>
                  </div>
                  {judgeResult.citations && judgeResult.citations.length > 0 && (
                    <div>
                      <span className="text-sm font-medium text-gray-700">根拠: </span>
                      <div className="space-y-2 mt-2">
                        {judgeResult.citations.slice(0, 5).map((citation: Citation, index: number) => (
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
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
