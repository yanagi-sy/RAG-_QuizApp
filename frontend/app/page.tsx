/**
 * ホームページ（トップ）
 * 【初心者向け】ルート / で表示。QA機能のQAPageを表示するだけのラッパー。
 */
import QAPage from "@/features/qa/QAPage";

export default function Home() {
  return <QAPage />;
}
