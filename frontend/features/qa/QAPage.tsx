"use client";

import { useState } from "react";
import AskForm from "./components/AskForm";
import RetrievalSlider from "./components/RetrievalSlider";
import AnswerView from "./components/AnswerView";
import { useAsk } from "./useAsk";

export default function QAPage() {
  const [retrievalValue, setRetrievalValue] = useState(0.5);
  const { loading, error, result, submit, retry } = useAsk();

  const handleSubmit = (question: string) => {
    // RetrievalSliderの値を使ってretrievalを計算
    const semantic = retrievalValue;
    const keyword = 1 - retrievalValue;
    submit(question, { semantic, keyword });
  };

  // INVALID_INPUTの場合はAnswerViewにerrorを渡さない（AskFormで表示するため）
  const displayError = error && error.code !== "INVALID_INPUT" ? error : null;

  return (
    <div className="min-h-dvh bg-gray-50 py-6 sm:py-8">
      <div className="max-w-5xl mx-auto px-4 sm:px-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-6 sm:mb-8">
          QA
        </h1>

        <div className="space-y-6">
          <RetrievalSlider
            value={retrievalValue}
            onChange={setRetrievalValue}
          />

          <AskForm onSubmit={handleSubmit} loading={loading} apiError={error} />

          {(loading || displayError || result) && (
            <AnswerView loading={loading} error={displayError} result={result} onRetry={retry} />
          )}
        </div>
      </div>
    </div>
  );
}
