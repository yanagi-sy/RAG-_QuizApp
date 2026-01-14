"use client";

interface JudgeButtonsProps {
  onJudge: (answer: boolean) => void;
  disabled?: boolean;
  loading?: boolean;
}

export default function JudgeButtons({
  onJudge,
  disabled = false,
  loading = false,
}: JudgeButtonsProps) {
  const isDisabled = disabled || loading;

  return (
    <div className="flex flex-wrap gap-4">
      <button
        onClick={() => onJudge(true)}
        disabled={isDisabled}
        className="flex-1 min-w-[140px] h-12 bg-green-600 text-white font-medium rounded-xl shadow-sm hover:bg-green-700 transition-colors focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed text-lg"
      >
        ○
      </button>
      <button
        onClick={() => onJudge(false)}
        disabled={isDisabled}
        className="flex-1 min-w-[140px] h-12 bg-red-600 text-white font-medium rounded-xl shadow-sm hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed text-lg"
      >
        ×
      </button>
    </div>
  );
}
