/**
 * QA用カスタムフック（質問送信・回答表示の状態とAPI呼び出し）
 * 【初心者向け】loading/error/result を保持。submit で /ask に質問を送り、
 * retrieval.semantic_weight で意味検索とキーワード検索のバランスを指定。retry/reset あり。
 */
import { useState } from "react";
import { askQuestion } from "@/lib/api";
import { ApiError, toApiError } from "@/lib/types";
import type { AskResponse } from "@/lib/types";

interface UseAskResult {
  loading: boolean;
  error: ApiError | null;
  result: AskResponse | null;
  submit: (question: string, retrieval?: { semantic_weight: number }) => Promise<void>;  // CHANGED: semantic_weightのみ
  retry: () => Promise<void>;
  reset: () => void;
}

export function useAsk(): UseAskResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [lastRetrieval, setLastRetrieval] = useState<{ semantic_weight: number } | undefined>(undefined);  // CHANGED: semantic_weightのみ

  const submit = async (
    question: string,
    retrieval?: { semantic_weight: number }  // CHANGED: semantic_weightのみ
  ) => {
    setLastQuestion(question);
    setLastRetrieval(retrieval);
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await askQuestion(question, retrieval);
      setResult(response);
    } catch (err) {
      // すべてのエラーをApiErrorに変換
      const apiError = toApiError(err);
      setError(apiError);
    } finally {
      setLoading(false);
    }
  };

  const retry = async () => {
    if (lastQuestion) {
      await submit(lastQuestion, lastRetrieval);
    }
  };

  const reset = () => {
    setLoading(false);
    setError(null);
    setResult(null);
    setLastQuestion(null);
    setLastRetrieval(undefined);
  };

  return {
    loading,
    error,
    result,
    submit,
    retry,
    reset,
  };
}
