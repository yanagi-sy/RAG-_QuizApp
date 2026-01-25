"use client";

/**
 * 検索バランススライダー（意味検索 vs キーワード検索）
 * 【初心者向け】0〜1 の値で semantic_weight を指定。QA送信時に /ask に渡す。
 */
interface RetrievalSliderProps {
  value: number;
  onChange: (value: number) => void;
}

export default function RetrievalSlider({
  value,
  onChange,
}: RetrievalSliderProps) {
  const semantic = value;
  const keyword = 1 - value;

  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 sm:p-6">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <span className="text-sm font-medium text-gray-700">
            意味検索
          </span>
          <span className="text-sm font-medium text-gray-700">
            キーワード検索
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
        />
        <div className="flex justify-between text-sm text-gray-600">
          <span>semantic={semantic.toFixed(2)}</span>
          <span>keyword={keyword.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
