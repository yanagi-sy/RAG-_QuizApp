/**
 * API型定義（リクエスト・レスポンス・エラーの型）
 * 【初心者向け】ApiError / Citation / AskRequest|Response / Quiz系 / Judge系 など。
 * バックエンドのスキーマと対応させ、型安全にAPIを利用する。
 */
// エラーコード型
export type ErrorCode = "INVALID_INPUT" | "NOT_FOUND" | "TIMEOUT" | "INTERNAL_ERROR" | "NETWORK_ERROR";

// ApiErrorクラス
export class ApiError extends Error {
  code: string;
  message: string;
  status?: number;

  constructor(code: string, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.message = message;
    this.status = status;
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  // ApiError形式のオブジェクトに変換（UI互換性のため）
  toErrorObject(): { error: { code: string; message: string } } {
    return {
      error: {
        code: this.code,
        message: this.message,
      },
    };
  }
}

// エラーレスポンス（APIから返ってくる形式）
export interface ApiErrorResponse {
  error: {
    code: ErrorCode | string;
    message: string;
  };
}

// ApiErrorかどうかを判定するヘルパー
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

// エラーをApiErrorに変換するヘルパー
export function toApiError(error: unknown): ApiError {
  if (isApiError(error)) {
    return error;
  }
  if (error && typeof error === "object" && "error" in error) {
    const errObj = error as { error?: { code?: string; message?: string } };
    if (errObj.error?.code && errObj.error?.message) {
      return new ApiError(errObj.error.code, errObj.error.message);
    }
  }
  return new ApiError("INTERNAL_ERROR", "不明なエラーが発生しました。");
}

// Citation型
export interface Citation {
  source: string;
  page: number | null; // PDFならページ番号、txtならnull
  quote: string;
}

// Ask API リクエスト
export interface AskRequest {
  question: string;
  retrieval?: {
    semantic_weight: number;  // CHANGED: semantic_weightのみ（keyword_weightはbackendで計算）
  };
}

// Ask API レスポンス
export interface AskResponse {
  answer: string;
  citations: Citation[];
}

// Level型
export type Level = "beginner" | "intermediate" | "advanced";

// Quiz API リクエスト
export interface QuizRequest {
  level: Level;
}

// Quiz API レスポンス
export interface QuizResponse {
  quiz_id: string;
  question: string;
}

// Judge API リクエスト
export interface JudgeRequest {
  quiz_id: string;
  answer: boolean; // true=○、false=×
}

// Judge API レスポンス
export interface JudgeResponse {
  is_correct: boolean;
  correct_answer: boolean;
  explanation: string;
  citations: Citation[];
}
