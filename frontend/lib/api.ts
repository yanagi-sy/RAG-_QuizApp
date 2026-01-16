/**
 * API呼び出し共通関数
 */

import { ApiError, type ApiErrorResponse } from "./types";

// 環境変数からbaseURLを取得（デフォルトはhttp://localhost:8000）
const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/**
 * 共通fetch関数
 * すべてのエラーケースでApiErrorをthrowする
 */
async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  let response: Response;

  try {
    response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });
  } catch (fetchError) {
    // fetch自体が失敗した場合（ネットワークエラーなど）
    throw new ApiError(
      "NETWORK_ERROR",
      "APIに接続できません。再試行してください。"
    );
  }

  // 404エラーでもJSONレスポンスを読む（バックエンドがJSON形式でエラーを返す場合）
  let data: unknown;
  try {
    data = await response.json();
  } catch (jsonError) {
    // JSONパースが失敗した場合
    if (!response.ok) {
      // JSONが読めない場合はHTTPステータスコードとステータステキストをフォールバック
      throw new ApiError(
        "INTERNAL_ERROR",
        `HTTP ${response.status}: ${response.statusText}`
      );
    } else {
      throw new ApiError(
        "INTERNAL_ERROR",
        "レスポンス形式が不正です。"
      );
    }
  }

  if (!response.ok) {
    // エラーレスポンスの形式を確認
    // 404でもJSONが返ってくる場合は、そのJSONを優先して使う
    if (
      data &&
      typeof data === "object" &&
      "error" in data &&
      data.error &&
      typeof data.error === "object" &&
      "code" in data.error &&
      "message" in data.error
    ) {
      const errorData = data as ApiErrorResponse;
      throw new ApiError(
        errorData.error.code,
        errorData.error.message,
        response.status
      );
    }
    // 予期しないエラー形式の場合（JSONは読めたが形式が違う）
    throw new ApiError(
      "INTERNAL_ERROR",
      `HTTP ${response.status}: ${response.statusText}`
    );
  }

  // 成功時もJSONが期待される形式でない可能性がある
  if (!data || typeof data !== "object") {
    throw new ApiError("INTERNAL_ERROR", "レスポンス形式が不正です。");
  }

  return data as T;
}

/**
 * POST /ask API呼び出し
 */
export async function askQuestion(
  question: string,
  retrieval?: { semantic_weight: number }  // CHANGED: semantic_weightのみ
): Promise<{ answer: string; citations: Array<{ source: string; page: number; quote: string }> }> {
  const body: { question: string; retrieval?: { semantic_weight: number } } = {  // CHANGED: semantic_weightのみ
    question,
  };
  if (retrieval) {
    body.retrieval = retrieval;
  }

  return fetchApi("/ask", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * POST /quiz API呼び出し
 */
export async function createQuiz(
  level: "beginner" | "intermediate" | "advanced"
): Promise<{ quiz_id: string; question: string }> {
  return fetchApi("/quiz", {
    method: "POST",
    body: JSON.stringify({ level }),
  });
}

/**
 * POST /judge API呼び出し
 */
export async function judgeAnswer(
  quiz_id: string,
  answer: boolean
): Promise<{
  is_correct: boolean;
  correct_answer: boolean;
  explanation: string;
  citations: Array<{ source: string; page: number; quote: string }>;
}> {
  return fetchApi("/judge", {
    method: "POST",
    body: JSON.stringify({ quiz_id, answer }),
  });
}
