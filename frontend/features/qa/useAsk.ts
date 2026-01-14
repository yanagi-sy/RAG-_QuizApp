/**
 * QA用カスタムフック
 */
import { useState } from "react";
import { askQuestion } from "@/lib/api";
import { ApiError, toApiError } from "@/lib/types";
import type { AskResponse } from "@/lib/types";

interface UseAskResult {
  loading: boolean;
  error: ApiError | null;
  result: AskResponse | null;
  submit: (question: string, retrieval?: { semantic: number; keyword: number }) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
}

export function useAsk(): UseAskResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [lastRetrieval, setLastRetrieval] = useState<{ semantic: number; keyword: number } | undefined>(undefined);

  const submit = async (
    question: string,
    retrieval?: { semantic: number; keyword: number }
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
