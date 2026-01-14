/**
 * Quiz用カスタムフック
 */
import { useState } from "react";
import { createQuiz, judgeAnswer } from "@/lib/api";
import { ApiError, toApiError } from "@/lib/types";
import type { Level, QuizResponse, JudgeResponse } from "@/lib/types";

interface UseQuizResult {
  level: Level;
  setLevel: (level: Level) => void;
  quizId: string | null;
  question: string | null;
  loadingGenerate: boolean;
  loadingJudge: boolean;
  generateError: ApiError | null;
  judgeError: ApiError | null;
  judgeResult: JudgeResponse | null;
  generateQuiz: () => Promise<void>;
  retryGenerate: () => Promise<void>;
  regenerateQuiz: () => Promise<void>;
  judge: (answer: boolean) => Promise<void>;
  retryJudge: () => Promise<void>;
  reset: () => void;
}

export function useQuiz(): UseQuizResult {
  const [level, setLevel] = useState<Level>("beginner");
  const [quizId, setQuizId] = useState<string | null>(null);
  const [question, setQuestion] = useState<string | null>(null);
  const [loadingGenerate, setLoadingGenerate] = useState(false);
  const [loadingJudge, setLoadingJudge] = useState(false);
  const [generateError, setGenerateError] = useState<ApiError | null>(null);
  const [judgeError, setJudgeError] = useState<ApiError | null>(null);
  const [judgeResult, setJudgeResult] = useState<JudgeResponse | null>(null);
  const [lastAnswer, setLastAnswer] = useState<boolean | null>(null);

  const generateQuiz = async () => {
    setLoadingGenerate(true);
    setGenerateError(null);
    setJudgeError(null);
    setJudgeResult(null);
    setQuizId(null);
    setQuestion(null);

    try {
      const response = await createQuiz(level);
      setQuizId(response.quiz_id);
      setQuestion(response.question);
    } catch (err) {
      // すべてのエラーをApiErrorに変換
      const apiError = toApiError(err);
      setGenerateError(apiError);
    } finally {
      setLoadingGenerate(false);
    }
  };

  const retryGenerate = async () => {
    await generateQuiz();
  };

  const regenerateQuiz = async () => {
    // 判定結果とエラーをクリアしてから再出題
    setJudgeError(null);
    setJudgeResult(null);
    await generateQuiz();
  };

  const judge = async (answer: boolean) => {
    if (!quizId) {
      return;
    }

    setLastAnswer(answer);
    setLoadingJudge(true);
    setJudgeError(null);
    setJudgeResult(null);

    try {
      const response = await judgeAnswer(quizId, answer);
      setJudgeResult(response);
    } catch (err) {
      // すべてのエラーをApiErrorに変換
      const apiError = toApiError(err);
      setJudgeError(apiError);
    } finally {
      setLoadingJudge(false);
    }
  };

  const retryJudge = async () => {
    if (quizId && lastAnswer !== null) {
      await judge(lastAnswer);
    }
  };

  const reset = () => {
    setQuizId(null);
    setQuestion(null);
    setLoadingGenerate(false);
    setLoadingJudge(false);
    setGenerateError(null);
    setJudgeError(null);
    setJudgeResult(null);
    setLastAnswer(null);
  };

  return {
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
    reset,
  };
}
